from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import NoAlertPresentException
from PIL import Image
import time
import os

driver = webdriver.Chrome()
driver.maximize_window()

driver.get(r"https://taaghche.com/login")
driver.set_page_load_timeout(7)
input("Login and then press enter > ")

folder_path = 'images/'
if os.path.exists(folder_path) and os.path.isdir(folder_path):
  for root, dirs, files in os.walk(folder_path, topdown=False):
    for name in files:
      os.remove(os.path.join(root, name))
    
    for name in dirs:
      os.rmdir(os.path.join(root, name))
  
  os.rmdir(folder_path)

os.makedirs(folder_path)

images = []

driver.get("https://taaghche.com/mylibrary?type=text")
driver.set_page_load_timeout(7)
input("If you've bought a book, just go to its reading page and Customize settings and then press enter > ")

# Convert Persian to English number
fa2en = lambda persian_number : ''.join({
  '۰': '0', '۱': '1', '۲': '2', '۳': '3', '۴': '4', '۵': '5', '۶': '6', '۷': '7', '۸': '8', '۹': '9'
}.get(char, char) for char in persian_number)

get_current_page = lambda : int(fa2en(driver.find_element(By.XPATH, r'//*[@id="pageNo"]').text))
get_total_pages = lambda : int(fa2en(driver.find_element(By.XPATH, r'//*[@id="totalPages"]').text))

prev_page = lambda : (driver.find_element(By.XPATH, r'//*[@id="___prevPageMobile"]') if ('mobile' in driver.find_element(By.TAG_NAME, "body").get_attribute("class")) else driver.find_element(By.XPATH, r'//*[@id="___prevPage"]')).click()
next_page = lambda : (driver.find_element(By.XPATH, r'//*[@id="___nextPageMobile"]') if ('mobile' in driver.find_element(By.TAG_NAME, "body").get_attribute("class")) else driver.find_element(By.XPATH, r'//*[@id="___nextPage"]')).click()

print("Don't touch WebDriver-screen !")

# resize screen to A5(1240, 1790); A4(2480, 3508) / 2 = A5(1240, 1790)
driver.set_window_size(1240, 1790)

current_page = get_current_page()
if current_page > True :
  print("Backing to first page...")
  for back_index in range(current_page):
    prev_page()
    time.sleep(0.6)

print("Saving pages...")
total_pages = get_total_pages()
for current_index in range(total_pages):
  while True:
    try:
      element = WebDriverWait(driver, 99999).until(EC.presence_of_element_located((By.XPATH, r'//*[@id="canvas0"]')))
      element.screenshot(f'images/test-{current_index+1}.png')
      break
    except:
      time.sleep(1)
  
  try:
    alert = driver.switch_to.alert
    print("Alert text:", alert.text)
    alert.accept()
    time.sleep(5)
  except NoAlertPresentException:
    # No alert present.
    time.sleep(1)
  
  file_name = os.path.abspath(f'images/{current_index+1}.png')
  canvas = driver.find_element(By.XPATH, r'//*[@id="canvas0"]')
  canvas.screenshot(file_name)
  images.append(file_name)  
  print(f"-> {file_name}")
  time.sleep(1)
  next_page()

driver.quit()

print("Converting to PDF...")
image_objects = []
for image in images:
  image_path = os.path.join(folder_path, image)
  img = Image.open(image_path)
  image_objects.append(img.convert('RGB'))

print("Saving...")
if image_objects:
  filename = time.strftime("%Y-%m-%d-%H-%M-%S", time.localtime()) + ".pdf"
  image_objects[0].save(filename, save_all=True, append_images=image_objects[1:], quality=100)
  print(f"BOOM! Book saved in `{os.path.abspath(filename)}` !")
else:
  ... # There are no images to convert."
