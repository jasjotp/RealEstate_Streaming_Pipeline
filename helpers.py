# helper functions to extract data 
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import os 
from openai import OpenAI
from dotenv import load_dotenv
import json 

load_dotenv()

# initialize our OpenAI client
OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
client = OpenAI(api_key = OPENAI_API_KEY)

# function to extract the bed, bath and sqft features from Zoopla if they exist, as they have the same class: _1wickv4
def extract_bed_bath_sqft(div):
    # default the beds, baths and sqft features to be N/A at first, as they will be overwritten later (if they exist)
    beds = baths = sqft = 'N/A'
    span_tags = div.find_all('span', class_ = '_1wickv4')
    
    # for each span tag (for beds, baths and sqt), extract the beds, baths, and sqft features if they exist in the text
    for tag in span_tags:
        text = tag.get_text(strip = True).lower()
        if 'bed' in text:
            beds = text 
        elif 'bath' in text:
            baths = text 
        elif 'sq. ft' in text or 'sq ft' in text:
            sqft = text 

    return beds, baths, sqft

# function to extract image URLs for listing 
def extract_images_from_listing(content: str) -> list:
    soup = BeautifulSoup(content, 'html.parser')
    image_urls = []

    # loop through each list item that contains picture tags with sources
    for li in soup.find_all('li'): 
        # find the picture tag inside the list tag 
        picture = li.find('picture')
        if picture:
            # prioritize grabbing the highest resolution jpg fallback
            source_tags = picture.find_all('source')

            for source in reversed(source_tags): # reversed, as typically, the last image is jpg format and typically highest resolution 
                if source.has_attr('srcset'):
                    srcset = source['srcset']
                    urls = [s.strip().split()[0] for s in srcset.split(',')]
                    if urls:
                        image_urls.append(urls[-1])
                        break # once we get one image for each picture tag, move on to the next picture, as we do not want duplicate images
    return image_urls

# function to extract property details using OpenAI
def extract_property_details(property_html: str) -> dict:
    print('Extracting property details...')

    # command to send to ChatGPT
    command = f"""
        You are an expert data extractor model and web scraper and you have been tasked with extracting information about the listing for me into JSON (if the detail exists, else put N/A).
        Return ONLY a JSON object with no explanation. Do not add markdown formatting or any text before/after.
        
        {property_html}

        This is the final json structure expected:
        {{
            "Address": "",
            "Price": "",
            "Description": "",
            "Beds": "",
            "Baths": "",
            "Receptions": "",
            "SqFt": "",
            "EPC Rating": "",
            "Tenure": "",
            "Time Remaining on Lease": "",
            "Service Charge": "",
            "Council Tax Band": "",
            "Ground Rent": ""    
        }}
    """

    try:
        response = client.chat.completions.create(
            model = "chatgpt-4o-latest",
            messages = [
                {
                    "role": "user",
                    "content": command
                }
            ]
        )
        output = response.choices[0].message.content.strip()

        json_data = json.loads(output)
        print(f'JSON OpenAI Output: {json_data}')
        return json_data 
    
    except Exception as e:
        print(f"Error extracting property details: {e}")
        return {}

# function to extract floor plan image 
def extract_floor_plan(html: str) -> str:
    print('Extracting floor plan...')

    soup = BeautifulSoup(html, 'html.parser')
    picture_tag = soup.find('picture')

    if picture_tag:
        source_tag = picture_tag.find('source')
        if source_tag and source_tag.has_attr('srcset'):
            srcset = source_tag['srcset']
            urls = [s.strip().split()[0] for s in srcset.split(',')]

            if urls:
                return urls[0] # grab first URL in srcset 
    
    # if there is no picture tag for the floor plan, return 'N/A'
    return 'N/A'



