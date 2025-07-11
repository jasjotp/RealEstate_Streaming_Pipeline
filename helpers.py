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