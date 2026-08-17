import json
import os

from bs4 import BeautifulSoup

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


driver = webdriver.Chrome()
base_dir = os.path.dirname(os.path.abspath(__file__))
folder = os.path.join(base_dir, "..", "data", "json")




def get_weg_talbe(table_page):
        try:
            dic = {}
            driver.get(table_page)
            
            wait=WebDriverWait(driver, 5)
            elemento= wait.until(EC.visibility_of_element_located (
                (By. CLASS_NAME,"clearfix" )))
            titulo =driver.title
            nome_arquivo=titulo.split(" ")[0]
            
            html=elemento.get_attribute("outerHTML")
            
            soup=BeautifulSoup(html , "html.parser")
            table_line_value= [td.get_text(strip=True)
                            for td in soup.find_all("td")]
            table_line_head = [th.get_text(strip=True)
                            for th in soup.find_all("th")]

            for head,value in zip(table_line_head, table_line_value):
                dic[head] = value
            
            os.makedirs(folder, exist_ok=True)
            
            path = os.path.join(folder, f"{nome_arquivo}.json")
            
            with open(path , "w", encoding = "utf-8") as f:
                json.dump(dic, f, ensure_ascii = False, indent = 4 )    
                
            driver.quit()
            response = print(f"{nome_arquivo}.json em {folder}")
            return response
        except Exception as e:
            
            print(f' Error: {e}')




def pages(url):
    try:
        next_pages={}
        url="https://www.weg.net/catalog/weg/BR/pt/Motores-El%C3%A9tricos/c/BR_MT"
        driver.get(url)
        
        wait = WebDriverWait(driver , 5)
        
        itens = driver.find_elements(
            By.CSS_SELECTOR, 'li[data-level="2"][class=""]')
        
        for li in itens:
            link = li.find_element(By.XPATH, './a')
            next_pages.append(link)
        
            

    except Exception as e:
        print("Tipo do erro:", type(e).__name__)
        print("Erro:", repr(e))
    
    