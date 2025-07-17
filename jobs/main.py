import asyncio
from playwright.async_api import async_playwright
import os 
from dotenv import load_dotenv
from bs4 import BeautifulSoup
from helpers import extract_bed_bath_sqft, extract_images_from_listing, extract_property_details, extract_floor_plan
from openai import OpenAI
from kafka import KafkaProducer 
import json 

load_dotenv()
AUTH = os.getenv('AUTH')
SBR_WS_CDP = f'wss://{AUTH}@brd.superproxy.io:9222'

# get the base URL to the REALTOR.ca site and the Location you want to scrape 
BASE_URL = 'https://www.zoopla.co.uk/'
LOCATION = 'London'

async def run(pw, producer):
    print('Connecting to Browser API...')
    browser = await pw.chromium.connect_over_cdp(SBR_WS_CDP)
    try:
        context = await browser.new_context()
        page = await context.new_page()

        print(f'Connected! Navigating to webpage: {BASE_URL}')
        await page.goto(BASE_URL, wait_until = 'load')

        # click on the Accept all to dismiss the cookies popup 
        try:
            await page.click("text='Accept all'", timeout = 5000)
            print("Clicked Accept all for Cookies")
        except:
            print("Accept all button not found or already dismissed")

        # fill in the location into the search bar and press enter 
        await page.wait_for_selector('input[name="autosuggest-input"]', timeout = 30000)

        await page.fill('input[name="autosuggest-input"]', LOCATION)
        await page.wait_for_timeout(1000)  # wait for suggestions to show
        await page.keyboard.press("Enter")
        print("Waiting for search results...")
        
        # wait for the page to load after you search the location 
        await page.wait_for_load_state('load')

        # pull the div that contains the regular listings for the page
        content = await page.inner_html('div[data-testid="regular-listings"]')

        # use bs4's HTML parser to pull the content from the page
        soup = BeautifulSoup(content, "html.parser")

        all_listings = []

        try:
            # each listing is in the 'dkr2t86' div class, so look through all the div classes that contain that div class
            for idx, div in enumerate(soup.find_all("div", class_ = "dkr2t86")): # gives us access to the index and value of all the divs containing each listing
                
                data = {}

                # extract address from address tag
                address_tag = div.find('address')
                address = address_tag.text.strip() if address_tag else 'N/A'

                # extract price from listing-price tag
                price_tag = div.find('p', {'data-testid': 'listing-price'})
                price = price_tag.text.strip() if price_tag else 'N/A'

                # extract the text from the description tag, and if there is no description tag, default to N/A
                description_tag = div.find('p', class_ = 'm6hnz63 _194zg6t9')
                description = description_tag.text.strip() if description_tag else 'N/A'
                
                # extract beds, baths, and sqft features if they exist using helper function from helpers.py
                beds, baths, sqft = extract_bed_bath_sqft(div)
                
                # extract the link to the posting
                link_tag = div.find('a')
                link = BASE_URL + link_tag['href'] if link_tag else 'N/A'

                # add the features to the data dictionary for each posting 
                data.update({
                    'Address': address,
                    'Price': price, 
                    'Description': description,
                    'Beds': beds, 
                    'Baths': baths,
                    'SqFt': sqft,
                    'Link': link
                })

                # navigate to the listings page 
                print(f'Navigating to the listing page at {link} in {address}')

                try:
                    # reconnect the browser 
                    await browser.close()
                    browser = await pw.chromium.connect_over_cdp(SBR_WS_CDP)
                    context = await browser.new_context()
                    detail_page = await context.new_page()
                
                    await detail_page.goto(data['Link'], wait_until = 'domcontentloaded', timeout = 30000)
                
                    # from the listing page, extract the images first
                    image_content = await detail_page.inner_html('div._15j4h5e0') 

                    listing_images = extract_images_from_listing(image_content)
                    if listing_images: 
                        data['Pictures'] = listing_images
                    else:
                        data['Pictures'] = []

                    # extract the main listing content using the OpenAI helper function from helpers.py
                    listing_content = await detail_page.inner_html('div[aria-label="Listing details"]')
                    property_details = extract_property_details(listing_content)
                    print(f'Property Details: {property_details}')
                    data.update(property_details)

                    # extract floor plan by clicking floor plan tab (button that opens the floor plan image)

                    # try to close any usercentrics banner  
                    try:
                        await detail_page.locator("aside#usercentrics-cmp-ui").evaluate("node => node.remove()")
                        print('Removed blocking overlay (usercentrics)...')
                    except:
                        pass 

                    # try to click floor plan button
                    try:
                        # Strategy 1 - Visible button text match
                        await detail_page.click("xpath=//*[contains(text(), 'Floor plan')]", timeout = 30000)
                        print("Clicked Floor Plan using XPath text match")
                    except:
                            try:
                                # Strategy 2 - Button class match
                                await detail_page.click("button._194zgEt9._1831lcw3", timeout = 30000)
                                print("Clicked Floor Plan using button class")
                            except:
                                try:
                                    # Strategy 3 - SVG icon inside the button (if visible)
                                    await detail_page.click("svg.k6cr000.k6cr002.k6cr005", timeout = 30000)
                                    print("Clicked Floor Plan using SVG icon")
                                except:
                                    try: 
                                        # Strategy 4 - Use the href anchor value from <use>
                                        await detail_page.click("use[href='#floorplan-medium']", timeout = 30000)
                                        print("Clicked Floor Plan using SVG href anchor")
                                    except Exception as e:
                                        print(f'All attempts failed to click Floor Plan: {e}')

                    # the floor plan is typically either an image viewer or a direct PDF link
                    try:
                        # after clicking the floor plan button, wait for the floor plan viewer content to appear 
                        await detail_page.wait_for_selector('ol[aria-label*="Floor plan"]', timeout = 30000)

                        # grab the MTML for just the floor plan section 
                        floor_plan_html = await detail_page.inner_html('ol[aria-label*="Floor plan"]')

                        # extract floor plan image URL 
                        floor_plan_url = extract_floor_plan(floor_plan_html)
                        print(f'Floor Plan URL (image viewer): {floor_plan_url}')

                        # add floor plan and property details to the JSON structure for each listing 
                        data['FloorPlanImage'] = floor_plan_url if floor_plan_url else 'N/A'

                        # send data to Kafka 
                        print('Sending data to Kafka')
                        producer.send('properties', value = json.dumps(data).encode('utf-8'))
                        print('Data sent to Kafka')

                    except:
                        try: # if the Floor plan label does not exist, the floor plan should be in a pdf
                            pdf_element = await detail_page.query_selector("a[href$='.pdf']")
                            pdf_url = await pdf_element.get_attribute('href') if pdf_element else None
                            print(f'Floor Plan URL (PDF): {pdf_url}')
                            data['FloorPlanImage'] = pdf_url if pdf_url else 'N/A'
                        except Exception as e:
                            print(f'Could not extract PDF Floor Plan: {e}')
                            data['FloorPlanImage'] = 'N/A'

                    await detail_page.close()
                    await context.close()
                    
                except Exception as e:
                    if "Page.navigate limit reached" not in str(e):
                        print(f'Error scraping detail page at {link}: {e}')
                    
                    # if we reach the limit error, extract whatever we can so we don't lose partial data
                    try:  # try to extract whatever images we can 
                        listing_images = extract_images_from_listing(image_content)
                        data['Pictures'] = listing_images
                    except:
                        data['Pictures'] = 'N/A'
                    
                    try: # try to extract whatever listing info from OpenAI that we can
                        listing_content = await detail_page.inner_html('div[aria-label="Listing details"]')
                        property_details = extract_property_details(listing_content)
                        data.update(property_details)
                    except: 
                        pass

                    try: # try to extract the floor plan contnet if anything else fails
                        # try clicking floor plan tab
                        await detail_page.click("xpath=//*[contains(text(), 'Floor plan')]", timeout = 30000)
                        print("Clicked Floor Plan in except block using XPath")

                        try: 
                            # try to extract floor plan from image viewer
                            # wait for the floor plan section to eppear 
                            await detail_page.wait_for_selector('ol[aria-label*="Floor plan"]', timeout = 30000)

                            # extract the floor plan image 
                            floor_plan_html = await detail_page.inner_html('ol[aria-label*="Floor plan"]', timeout = 30000)
                            floor_plan_url = extract_floor_plan(floor_plan_html)
                            print(f'Floor Plan URL (image viewer): {floor_plan_url}')
                            data['FloorPlanImage'] = floor_plan_url if floor_plan_url else 'N/A'
                        except: 
                            # if the image viewer fails, try to grab the PDF link 
                            try: 
                                pdf_element = await detail_page.query_selector("a[href$='.pdf']")
                                pdf_url = await pdf_element.get_attribute('href') if pdf_element else None 
                                print(f'Floor Plan URL (PDF): {pdf_url}')
                                data['FloorPlanImage'] = pdf_url if pdf_url else 'N/A'
                            except Exception as e:
                                print(f'Could not extract PDF Floor Plan: {e}')
                                data['FloorPlanImage'] = 'N/A'
                    except: 
                        data['FloorPlanImage'] = 'N/A'

                # append each listing to our result set 
                all_listings.append(data)
                await asyncio.sleep(1)
            
                print(f'Scraped listing {idx+1}: {address}')

        except Exception as e:
            print(f'Fatal scraping error: {e}')
        finally:
            # save all listings so far to a JSON file 
            with open('listings.json', 'w', encoding = 'utf-8') as f:
                json.dump(all_listings, f, ensure_ascii = False, indent = 2)
            print(f'Saved {len(all_listings)} listings to listings.json')

    finally:
        # only close the initial context/page if still open
        try:
            await context.close()
        except:
            pass
        try:
            await browser.close()
        except:
            pass

async def main():
    producer = KafkaProducer(
        bootstrap_servers = ['localhost:9092'], 
        max_block_ms = 5000
    )

    async with async_playwright() as playwright:
        await run(playwright, producer)

if __name__ == '__main__':
    asyncio.run(main())