# helper functions to extract data 
import asyncio
from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
import os 

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