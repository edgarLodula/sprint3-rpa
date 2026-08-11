from bs4 import BeautifulSoup
import requests


def get_all_html(url:str)-> str:
    html_page=requests.get(url=url, auth=('user','pass'))
    soup = BeautifulSoup(html_page.text,'html.parser')

    return html_page.text