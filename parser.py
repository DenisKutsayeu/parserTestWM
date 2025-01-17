import json
import os
import re
import shutil
from random import choice
from typing import Dict, List, Tuple, Union

import requests
from loguru import logger
from parsel import Selector

MAIN_URL = "https://www.truckscout24.de"
BASE_FOLDER = "data"
JSON_PATH = "data/data.json"


def xpath(text: str, query: str) -> Selector:
    return Selector(text=text).xpath(query=query)


def send_request(url, params=None) -> str:
    if not url.startswith("https://cdn"):
        url = f"{MAIN_URL}{url}"
    response = requests.get(url, params=params)
    if response.status_code == 200:
        return response
    else:
        response.raise_for_status()


def get_page_links(response: str) -> List[str]:
    all_page_links = xpath(
        response,
        "//section[@id='offer-list-pagination']//li[contains(@class, 'page-item')]//a/@href",
    ).getall()
    unique_page_links = sorted(set(all_page_links[1:]))
    return unique_page_links


def parse_pages(page_links: List[str]) -> None:
    data = {"ads": []}
    for page_link_part in page_links:
        try:
            response = send_request(url=page_link_part).text
        except Exception as e:
            logger.error(f"Произошла ошибка: {e}. {type(e)}")

        item_hrefs = xpath(
            response, "//section[@id='offer-list']//section[@class='grid-body']/a/@href"
        ).getall()
        item_data = parse_random_item(item_href=choice(item_hrefs))
        data["ads"].append(item_data)
    create_json_file(data)


def parse_random_item(item_href: str) -> Dict[str, Union[int, str]]:
    try:
        response = send_request(url=item_href).text
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}. {type(e)}")

    id = xpath(response, "//section[@id='top-data']//h1//@data-listing-id").get()
    href = f"{MAIN_URL}{item_href}"
    title = " ".join(
        map(
            lambda x: x.strip(),
            xpath(
                response, "//section[@id='top-data']//div[@class='d-flex']//text()"
            ).getall()[1:],
        )
    )
    price_str = xpath(
        response,
        "//section[@id='top-data']//div[@class='fs-5 max-content my-1 word-break fw-bold']//text()",
    ).get(default="0")

    price = int(re.sub(r".+?(\d+)\.?(\d+).+", r"\1\2", price_str, flags=re.DOTALL))

    mileage = 0
    power = 0
    color = ""
    tech_details = xpath(response, "//div[@id='properties']//dl").getall()
    for tech_detail in tech_details:
        dt_text = xpath(tech_detail, "//dt//text()").get()
        dd_text = xpath(tech_detail, "//dd//text()").get()
        if "kilometerstand" in dt_text.lower():
            mileage = int(re.sub(r".*?(\d+)\.?(\d+)?.*", r"\1\2", dd_text))
        elif "leistung" in dt_text.lower():
            power = round(float(re.sub(r"(\d+),?(\d*)\skW.+", r"\1.\2", dd_text)))
        elif "farbe" in dt_text.lower():
            color = dd_text

    description = "".join(
        xpath(
            response, "//div[@id='description']//div[@class='col beschreibung']//text()"
        ).getall()
    ).strip()
    phone = parse_phones(id)
    images_links = parse_images(id)
    download_images(images_links, folder_name=id)

    item_data = {
        "id": int(id),
        "href": href,
        "title": title,
        "price": price,
        "mileage": mileage,
        "color": color,
        "power": power,
        "description": description,
        "phone": phone,
    }

    return item_data


def parse_phones(id: str) -> str:
    params = {
        "listing_id": id,
        "messageType": "CALLBACK",
        "event_source": "CALL_BACK_PROVIDER_INFO_NUMBER",
        "event_context": "LISTING_DETAIL",
        "action_path": "/inquiry/listing-inquiry/submit",
        "validation_path": "/inquiry/listing-inquiry/validate",
        "revoke_path": "/inquiry/listing-inquiry/revoke",
    }
    try:
        response = send_request(
            url="/inquiry/listing-inquiry/get-ajax-form", params=params
        ).text
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}. {type(e)}")

    phone = xpath(response, "//ul[@class='list-group list-group-flush']//a/text()").get(
        default=""
    )
    return phone


def parse_images(id: str) -> Tuple[str, str, str]:
    params = {
        "id": id,
        "eventContext": "LISTING_DETAIL",
        "mainCategory": "7_Transportfahrzeuge,Nutzfahrzeuge",
    }
    try:
        response = send_request(
            url="/listing/display/ajax-listing-modal", params=params
        ).text
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}. {type(e)}")

    images_links = xpath(
        response, "//div[@class='keen-slider keen-slider-uninitialized']//@src"
    ).getall()
    images_links_hdv = tuple(filter(lambda i: "hdv" in i, images_links))[:3]
    return images_links_hdv


def download_images(images_urls: Tuple[str, str, str], folder_name: str) -> None:
    folder_path = os.path.join(BASE_FOLDER, folder_name)
    os.makedirs(folder_path)

    for number, url in enumerate(images_urls, start=1):
        try:
            response = send_request(url)
        except Exception as e:
            logger.error(f"Произошла ошибка: {e}. {type(e)}")

        filename = f"image-{number}.jpg"
        filepath = os.path.join(folder_path, filename)

        with open(filepath, "wb") as f:
            f.write(response.content)
        logger.info(f"Скачано изображение: {filename} объявления: {folder_name}")


def create_json_file(data: Dict[str, Union[int, str]]) -> None:
    with open(JSON_PATH, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=3)
    logger.info("Данные успешно записаны!")


def main():
    if os.path.exists(BASE_FOLDER):
        shutil.rmtree(BASE_FOLDER)
    os.makedirs(BASE_FOLDER)
    try:
        response = send_request(
            url="/transporter/gebraucht/kuehl-iso-frischdienst/renault"
        ).text
        page_links = get_page_links(response)
        parse_pages(page_links)
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}. {type(e)}")


if __name__ == "__main__":
    main()
