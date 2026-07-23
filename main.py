import os
import requests
from PIL import Image
from io import BytesIO
from datetime import datetime, timedelta
import json
import logging

# 日志配置
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 路径配置
STATIC_FOLDER = "static"
PICTURE_FOLDER = os.path.join(STATIC_FOLDER, "picture")
INDEX_PATH = os.path.join(PICTURE_FOLDER, "index.json")

# 确保文件夹存在
os.makedirs(PICTURE_FOLDER, exist_ok=True)

def download_bing_image(date_str):
    """根据日期下载指定日期的必应壁纸"""
    try:
        # 构造日期参数
        url = f"https://www.bing.com/HPImageArchive.aspx?format=js&idx=0&n=8&uhd=1&mkt=zh-CN"
        resp = requests.get(url)
        resp.raise_for_status()
        data = resp.json()
        
        # 查找匹配日期的图片
        for image in data["images"]:
            if image["enddate"] == date_str.replace("-", ""):
                urlbase = image["urlbase"]
                high_res_url = f"https://www.bing.com{urlbase}_UHD.jpg"
                fallback_url = f"https://www.bing.com{urlbase}_1920x1080.jpg"
                
                test_resp = requests.head(high_res_url)
                image_url = high_res_url if test_resp.status_code == 200 else fallback_url
                
                return {
                    "date": date_str,
                    "url": image_url,
                    "copyright": image.get("copyright", ""),
                    "urlbase": urlbase
                }
        return None
    except Exception as e:
        logging.error(f"下载 {date_str} 图片失败: {e}")
        return None

def fetch_images_for_days(days=30):
    """获取过去 N 天的图片"""
    images = []
    today = datetime.now()
    
    for i in range(days):
        date = today - timedelta(days=i)
        date_str = date.strftime("%Y-%m-%d")
        logging.info(f"正在获取 {date_str} 的图片...")
        
        # 尝试获取图片
        img_info = download_bing_image(date_str)
        if img_info:
            images.append(img_info)
            logging.info(f"成功获取 {date_str} 的图片")
        else:
            logging.warning(f"未找到 {date_str} 的图片")
    
    return images

def download_image(url):
    """下载图片并返回PIL Image对象"""
    try:
        resp = requests.get(url)
        resp.raise_for_status()
        return Image.open(BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        logging.error(f"下载图片失败: {e}")
        return None

def load_existing_index():
    """加载现有的index.json文件"""
    if not os.path.exists(INDEX_PATH):
        return []
    
    try:
        with open(INDEX_PATH, "r", encoding="utf-8") as f:
            logging.info("加载现有index.json成功")
            return json.load(f)
    except Exception as e:
        logging.error(f"加载现有index.json失败: {e}")
        return []

def save_image(img, filepath):
    """保存图片到指定路径"""
    try:
        max_width, max_height = 2560, 1600
        img.thumbnail((max_width, max_height))
        img.save(filepath, "WEBP", quality=80, method=6)
        logging.info(f"保存图片 {filepath}")
        return True
    except Exception as e:
        logging.error(f"保存图片失败 {filepath}: {e}")
        return False

def merge_and_update_images(new_images, existing_index):
    """合并新图片和现有索引，并更新文件"""
    today_str = datetime.now().strftime("%Y-%m-%d")
    logging.info(f"今天的日期: {today_str}")
    updated_index = []
    existing_dates = {item["date"] for item in existing_index}
    
    for img_info in new_images:
        date = img_info["date"]
        logging.info(f"处理图片: {date}")
        if date in existing_dates:
            logging.info(f"图片 {date} 已存在，跳过")
            continue
            
        filename = f"{date}.webp"
        filepath = os.path.join(PICTURE_FOLDER, filename)
        
        img = download_image(img_info["url"])
        if img is None:
            continue
            
        if not save_image(img, filepath):
            continue
            
        if date == today_str:
            logging.info("保存今天的图片为 daily.webp / daily.jpeg / original.jpeg")
            save_image(img, os.path.join(STATIC_FOLDER, "daily.webp"))
            img.save(os.path.join(STATIC_FOLDER, "daily.jpeg"), "JPEG", quality=95, optimize=True)
            img.save(os.path.join(STATIC_FOLDER, "original.jpeg"), "JPEG", quality=100)
            logging.info("保存了 daily.webp / daily.jpeg / original.jpeg")
            
        updated_index.append({
            "filename": filename,
            "date": date,
            "path": f"/picture/{filename}",
            "copyright": img_info.get("copyright", ""),
            "url": img_info.get("url", "")
        })
    
    combined_index = existing_index + updated_index
    combined_index.sort(key=lambda x: x["date"], reverse=True)
    
    thirty_days_ago = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    filtered_index = []
    removed_files = set()
    
    for item in combined_index:
        if item["date"] > thirty_days_ago:
            filtered_index.append(item)
        else:
            removed_files.add(os.path.join(PICTURE_FOLDER, item["filename"]))
            logging.info(f"图片 {item['date']} 超过30天，标记为删除")
    
    for filepath in removed_files:
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
                logging.info(f"删除旧图片: {filepath}")
        except Exception as e:
            logging.error(f"删除旧图片失败 {filepath}: {e}")
    
    return filtered_index

def update_index(index_list):
    """更新index.json文件"""
    try:
        with open(INDEX_PATH, "w", encoding="utf-8") as f:
            json.dump(index_list, f, ensure_ascii=False, indent=2)
        logging.info(f"已更新 index.json，共 {len(index_list)} 项")
    except Exception as e:
        logging.error(f"更新index.json失败: {e}")

def main():
    logging.info("开始获取 Bing 图片...")
    existing_index = load_existing_index()
    
    # 如果索引为空（首次运行），获取30天；否则只获取最新的
    if not existing_index:
        logging.info("首次运行，获取过去30天的图片...")
        # 直接获取过去30天的图片
        new_images = fetch_images_for_days(30)
    else:
        logging.info("日常更新，只获取今天的图片...")
        # 只获取今天的
        today = datetime.now().strftime("%Y-%m-%d")
        new_images = []
        img_info = download_bing_image(today)
        if img_info:
            new_images.append(img_info)
    
    if not new_images:
        logging.error("未获取到任何新图像信息")
        return

    updated_index = merge_and_update_images(new_images, existing_index)
    update_index(updated_index)
    logging.info("更新完成！")

if __name__ == "__main__":
    main()
