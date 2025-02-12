import time
import redis
from curl_cffi import requests
import json
import re
from datetime import datetime
from DrissionPage import ChromiumOptions, WebPage
from retrying import retry
from urllib.parse import urlparse, parse_qs

r = redis.StrictRedis(host='localhost', port=6379, db=0)

def get_redirect_url(begin_location: str, end_location: str, begin_date: str) -> str:
    """
    获取重定向 URL
    
    :param begin_location: 出发地
    :param end_location: 目的地
    :param begin_date: 出发日期，格式为 YYYYMMDD
    :return: 重定向 URL 字符串
    """
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'zh-CN,zh;q=0.9,fr;q=0.8,en;q=0.7,zh-TW;q=0.6',
        'cache-control': 'no-cache',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://www.cathaypacific.com/cx/sc_CN.html',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-origin',
        'sec-fetch-user': '?1',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    }

    params = {
        'ACTION': 'SINGLECITY_SEARCH',
        'ENTRYPOINT': 'https://www.cathaypacific.com/cx/sc_CN.html',
        'ENTRYLANGUAGE': 'sc',
        'ENTRYCOUNTRY': 'CN',
        'RETURNURL': 'https://www.cathaypacific.com/cx/sc_CN.handler.html',
        'ERRORURL': 'https://www.cathaypacific.com/cx/sc_CN.handler.html',
        'BOOKING_FLOW': 'REVENUE',
        'ORIGIN': begin_location,
        'DESTINATION': end_location,
        'DEPARTUREDATE': begin_date,
        'TRIPTYPE': 'O',
        'CABINCLASS': 'Y',
        'ADULT': '1',
        'YOUNGADULT': '0',
        'CHILD': '0',
        'INFANT': '0',
        'DISCOUNTCODE': '',
        'USERID': '',
        'NAMSESSIONID': '',
        'NAMURL': '',
        'FLEXIBLEDATE': 'true',
        'INSTANTSEARCHPRICE': '',
    }

    response = requests.get(
        'https://www.cathaypacific.com/wdsibe/IBEFacade', 
        params=params, 
        headers=headers,
        impersonate="chrome")

    if response.status_code == 200:    
        return response.url
    else:
        raise Exception(f"Error fetching redirect URL: {response.text}")

def parse_url(redirect_url: str) -> tuple[str, str, str]:  
    """
    从重定向 URL中提取参数
    
    :param redirect_url: 重定向 URL
    :return: 包含 sid、rawParams 和 signature 的元组
    """
    parsed_url = urlparse(redirect_url)
    query_string = parsed_url.fragment.split('?')[-1]
    query_dict = parse_qs(query_string)

    query_params = {k: v[0] for k, v in query_dict.items()}

    sid = query_params['sid']
    brand = query_params['brand']
    locale = query_params['locale']
    portAndCabinCode = query_params['portAndCabinCode']

    rawParams = sid + "_" + brand + "_" + locale + "_" + portAndCabinCode
    signature = query_params["signature"]

    return sid, rawParams, signature

def get_enc(sid: str, rawParams: str, signature: str) -> dict:
    """
    获取enc参数并格式化请求搜索结果页html的载荷
    
    :param sid, rawParams, signature: 请求搜索结果页html所需参数
    :return: 请求搜索结果页html所需载荷
    """
    headers = {
        'accept': 'application/json, text/plain, */*',
        'accept-language': 'zh-CN,zh;q=0.9,fr;q=0.8,en;q=0.7,zh-TW;q=0.6',
        'cache-control': 'no-cache',
        'content-type': 'application/json',
        'ibe-brand': 'CX',
        'origin': 'https://www.cathaypacific.com',
        'pragma': 'no-cache',
        'priority': 'u=1, i',
        'referer': 'https://www.cathaypacific.com/ibe/',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'empty',
        'sec-fetch-mode': 'cors',
        'sec-fetch-site': 'same-origin',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
        'x-auth-token': sid,
    }

    data = {
        'rawParams': rawParams,
        'signature': signature,
    }

    response = requests.post(
    'https://www.cathaypacific.com/ibe/api/v1.0/flightSearch/singleCitySearch',
    headers=headers,
    data=json.dumps(data),
    impersonate="chrome"
    )

    if response.status_code != 200:
        raise Exception(f"Error getting enc parameters: {response.text}")

    res = response.json()
    return {
        'LANGUAGE': res["language"],
        'SITE': res["site"],
        'SERVICE_ID': res["serviceId"],
        'EMBEDDED_TRANSACTION': res["embeddedTransation"],
        'ENCT': res["enct"],
        'ENC': res["enc"],
    }

def store_cookies_in_redis(cookies: list) -> None:
    """将获取的cookies存储到Redis中
    
    :param cookies: DrissionPage读取的搜索结果页cookies列表
    """
    for cookie in cookies:
        if cookie['name'] == 'reese84':
            r.set('reese84', cookie['value'])  
            r.expire('reese84', 600)  # 设置过期时间为600秒（10分钟）

def get_reese84() -> None:
    """获取新的 reese84 值并存入 Redis，设置过期时间为600秒（10分钟）"""
    co = ChromiumOptions().auto_port()
    co.incognito()
    
    page = WebPage(chromium_options=co)
    page.get('https://www.cathaypacific.com/cx/sc_CN.html')
    
    # 同意 Cookie 设置
    if page.ele('xpath://button[@class="accept-recommended-btn-handler"]').text in ['全部同意', 'Accept all']:
        page.ele('xpath://button[@class="accept-recommended-btn-handler"]').click()

    # 输入目的地
    input_dest = page.ele('xpath:/html/body/div[1]/div/div/div[1]/div[2]/div[1]/div[2]/div[1]/div[2]/div/div[2]/div[1]/div/div[1]/div[2]/div[2]/input')  
    input_dest.scroll.to_bottom()

    input_dest.click()
    input_dest.input('FCO')
    dest_confirm = page.ele('xpath:/html/body/div[1]/div/div/div[1]/div[2]/div[1]/div[2]/div[1]/div[2]/div/div[2]/div[1]/div/div[1]/div[2]/div[3]/div/div/li/span[1]/span/span[1]')
    dest_confirm.click()
    # 点击日期选择按钮
    depart_btn = page.ele('xpath:/html/body/div[1]/div/div/div[1]/div[2]/div[1]/div[2]/div[1]/div[2]/div/div[2]/div[1]/div/div[3]/div/div[1]/div')
    depart_btn.click()

    date_btn = page.ele('xpath:/html/body/div[1]/div/div/div[1]/div[2]/div[1]/div[2]/div[1]/div[2]/div/div[2]/div[1]/div/div[3]/div/div[3]/div[2]/div[2]/div/div/div[1]/table/tbody//button[@class="rdp-button_reset rdp-button rdp-day"]', index=-1)
    time.sleep(1)
    date_btn.click()

    time.sleep(1)
    arrival_btn = page.ele('xpath:/html/body/div[1]/div/div/div[1]/div[2]/div[1]/div[2]/div[1]/div[2]/div/div[2]/div[1]/div/div[3]/div/div[2]')
    arrival_btn.ele('xpath:/div').click()

    date_btn = page.ele('xpath:/html/body/div[1]/div/div/div[1]/div[2]/div[1]/div[2]/div[1]/div[2]/div/div[2]/div[1]/div/div[3]/div/div[3]/div[2]/div[2]/div/div/div[2]/table/tbody//button[@class="rdp-button_reset rdp-button rdp-day"]', index=-1)
    time.sleep(1)
    date_btn.click()

    # 日期确认
    page.ele('xpath:/html/body/div[1]/div/div/div[1]/div[2]/div[1]/div[2]/div[1]/div[2]/div/div[2]/div[1]/div/div[3]/div/div[3]/div[3]/div/div/button/div/span').click()
    
    # 提交
    page.scroll.up(300)
    time.sleep(1)
    page.ele('@text()=搜索航班').click()

    page.wait.url_change('https://book.cathaypacific.com/CathayPacificV3/dyn/air/booking/owdAvail')
    page.wait(8)

    store_cookies_in_redis(page.cookies())

def use_reese84() -> str:
    """
    获取 reese84 的值，如果值已过期则重新生成
    
    :return: 包含 reese84 的 cookie 字典
    """
    reese84_value = r.get('reese84')
    
    if reese84_value is None:
        print("reese84 已过期或不存在，正在生成新的值...")
        get_reese84()  
        reese84_value = r.get('reese84')
        
    cookies = {
        'reese84': reese84_value.decode('utf-8')  # decode 到字符串
    }
    return cookies

@retry(stop_max_attempt_number=5, wait_fixed=2000)
def visit_booking_page(data: dict, cookies: dict, session: requests.Session) -> requests.Response:
    """
    访问搜索结果页，并返回响应对象

    :param data: 请求载荷
    :param cookies: 必需reese84的cookies 字典
    :param session: requests 会话对象
    :return: requests.Response 对象
    """
    headers = {
        'accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'accept-language': 'zh-CN,zh;q=0.9,fr;q=0.8,en;q=0.7,zh-TW;q=0.6',
        'cache-control': 'no-cache',
        'content-type': 'application/x-www-form-urlencoded',
        'origin': 'https://www.cathaypacific.com',
        'pragma': 'no-cache',
        'priority': 'u=0, i',
        'referer': 'https://www.cathaypacific.com/',
        'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"macOS"',
        'sec-fetch-dest': 'document',
        'sec-fetch-mode': 'navigate',
        'sec-fetch-site': 'same-site',
        'upgrade-insecure-requests': '1',
        'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    }

    response = session.post(
        'https://book.cathaypacific.com/CathayPacificV3/dyn/air/booking/owdAvail', # postUrl
        cookies=cookies,
        headers=headers,
        data=data,
        impersonate="chrome"
    )    
    response.raise_for_status()  # 如果请求失败则抛出异常
    return response

def extract_ids(html_string: str) -> tuple:
    """
    从 HTML 字符串中提取 EXTERNAL_ID 和 TAB_ID

    :param html_string: HTML 内容字符串
    :return: 包含 external_id 和 tab_id 的元组
    """
    external_id_pattern = r'\\?"EXTERNAL_ID\\?":\\?"([^\\"]+)"'
    tab_id_pattern = r'\\?"TAB_ID\\?":\\?"([^\\"]+)"'

    external_id_match = re.search(external_id_pattern, html_string)
    tab_id_match = re.search(tab_id_pattern, html_string)

    external_id = external_id_match.group(1) if external_id_match else None
    tab_id = tab_id_match.group(1) if tab_id_match else None

    return external_id, tab_id

def send_request(session: requests.Session, cookies: dict, params: dict, data: dict) -> requests.Response:
    """
    请求航班数据接口并返回响应对象

    :param session: requests 会话对象，与请求html时保持同一
    :param cookies: 必需reese84和JSESSIONID_CathayPacificV3的cookies 字典
    :param params: key为TAB_ID的字典
    :param data: 请求载荷
    :return: 响应对象
    """
    headers = {
    'accept': 'application/json, text/plain, */*',
    'accept-language': 'zh-CN,zh;q=0.9,fr;q=0.8,en;q=0.7,zh-TW;q=0.6',
    'cache-control': 'no-cache',
    'content-type': 'application/x-www-form-urlencoded',
    'origin': 'https://book.cathaypacific.com',
    'pragma': 'no-cache',
    'priority': 'u=1, i',
    'referer': 'https://book.cathaypacific.com/CathayPacificV3/dyn/air/booking/owdAvail',
    'sec-ch-ua': '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"macOS"',
    'sec-fetch-dest': 'empty',
    'sec-fetch-mode': 'cors',
    'sec-fetch-site': 'same-origin',
    'user-agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36',
    }

    response = session.post(
        'https://book.cathaypacific.com/CathayPacificV3/dyn/air/booking/owdUpsell',
        params=params,
        cookies=cookies,
        headers=headers,
        data=data,
        impersonate = "chrome"
    )
    response.raise_for_status()  
    return response

def format_std_dt(ts: int) -> str:
    """
    将时间戳格式化为标准日期时间格式

    :param ts: 时间戳（毫秒）
    :return: 格式化后的日期时间字符串
    """
    t = time.localtime(ts / 1000 - 8 * 3600)  # 减去8小时
    return time.strftime('%Y-%m-%d %H:%M:%S', t)

def convert_time(time_str: str) -> str:
    """
    将时间字符串转换为标准时间格式

    :param time_str: 时间字符串（日月年时分格式）
    :return: 格式化后的日期时间字符串（'%Y-%m-%d %H:%M:%S'）
    """
    year = int(time_str[4:8])
    month = int(time_str[2:4])
    day = int(time_str[0:2])
    hour = int(time_str[8:10])
    minute = int(time_str[10:12])

    date_time = datetime(year, month, day, hour, minute)
    formatted_date_time = date_time.strftime('%Y-%m-%d %H:%M:%S')
    return formatted_date_time

def parse_mapping(res: dict) -> dict:
    """
    解析航班映射信息
    
    :param res: 包含航班数据的字典
    :return: 解析后的航班映射字典
    """
    RECO_FLIGHTS_MAPPING = json.loads(res['DDSContext']['RECO_FLIGHTS_MAPPING'])
    reco_flight_mapping = {}

    for key, value in RECO_FLIGHTS_MAPPING.items():
        mapping_info = []
        
        for item in value["0"]:
            parts = item.split('_')
            if len(parts) < 4:
                continue
            time_strings = parts[5].split(',')
            departure_time = convert_time(time_strings[0])
            arrival_time = convert_time(time_strings[1])       
            formatted_info = {
                'flight_code': parts[2],
                'departure_time': departure_time,
                'arrival_time': arrival_time,
            }
            mapping_info.append(formatted_info)

        reco_flight_mapping[key] = mapping_info
    
    return reco_flight_mapping

def format_price(price_str: str) -> str:
    """
    格式化价格字符串

    :param price_str: 原始价格字符串（0000）
    :return: 格式化后的价格字符串(0,000)
    """   
    numeric_part = price_str[3:-1]  
    
    if len(numeric_part) >= 4:  
        modified_numeric_part = numeric_part[:-3] + ',' + numeric_part[-3:]
    else:
        modified_numeric_part = numeric_part  
    
    return price_str[:3] + modified_numeric_part + price_str[-1]

def match_price(res: dict, reco_flight_mapping: dict, match_info: dict) -> dict:
    """
    将特定出发到达时间的航班号与价格信息匹配

    :param res: 响应数据字典
    :param reco_flight_mapping: 航班映射字典
    :param match_info: 待匹配的航班信息字典
    :return: 更新后的匹配信息字典
    """
    reco_price = res['pageBom']['modelObject']['availabilities']['upsell']['recommendations'] 
    min_price = float('inf')  # Start with infinity
    
    for reco_id, flights_eles in reco_flight_mapping.items():
        for flight_eles in flights_eles:
            # Check if all three keys match
            if (flight_eles['departure_time'] == match_info['departure_time'] and
                flight_eles['arrival_time'] == match_info['arrival_time'] and
                flight_eles['flight_code'] == match_info['flight_code']):
                
                # Get the corresponding recommendation price
                amount = reco_price[reco_id]['recommendationPrice']['price']['totalPrice']['cashAmount']['amount']
                if amount < min_price:
                    min_price = amount
                
    if min_price != float('inf'):
        match_info['price'].append(min_price)
        
    return match_info

def parse_flights(res: dict, reco_flight_mapping: dict) -> list:
    """
    解析航班数据并返回格式化结果

    :param res: 响应数据字典
    :param reco_flight_mapping: 航班映射字典
    :return: 格式化后的航班信息列表
    """
    data = res['pageBom']['modelObject']['availabilities']['upsell'] 
    flights = data['bounds'][0]['flights']
    
    data_list = []
    for flight in flights:
        segments = flight['segments']
        seg = segments[0]
        destinationDate = format_std_dt(seg['destinationDate'])
        flightIdentifier = seg['flightIdentifier']
        originDate = format_std_dt(flightIdentifier['originDate'])
        flightNumber = flightIdentifier['marketingAirline'] + flightIdentifier['flightNumber']
        
        formatted_flight = {
            '出发': seg['originLocation'],
            '到达': seg['destinationLocation'],
            '航班': flightNumber,
            '时间': (" -> ").join([originDate, destinationDate]),
        }
        
        match_info = {
            'departure_time': originDate,
            'arrival_time': destinationDate,
            'flight_code': flightNumber,
            'price': []
        }
        match_info = match_price(res, reco_flight_mapping, match_info)
        formatted_flight["票价"] = format_price(f"CNY{min(match_info['price'])}起") if match_info['price'] else "无票价"
        data_list.append(formatted_flight)

    return data_list

def input_and_search(begin_location: str, end_location: str, begin_date: str) -> None:
    """
    根据用户输入的出发地、目的地和出发时间进行航班搜索

    :param begin_location: 出发地
    :param end_location: 目的地
    :param begin_date: 出发日期
    """
    try:
        redirect_url = get_redirect_url(begin_location, end_location, begin_date)
        sid, rawParams, signature = parse_url(redirect_url)

        data = get_enc(sid, rawParams, signature)
        cookies = use_reese84()  
        session = requests.Session()

        response = visit_booking_page(data, cookies, session)
        
        # 获取 JSESSIONID
        JSESSIONID_CathayPacificV3 = response.cookies.get("JSESSIONID_CathayPacificV3")
        cookies['JSESSIONID_CathayPacificV3'] = JSESSIONID_CathayPacificV3

        external_id, tab_id = extract_ids(response.text)
        params = {
            'TAB_ID': tab_id,
        }
        
        data = {
            'EMBEDDED_TRANSACTION': 'FlexPricerAvailabilityBoundCalculation',
            'BOUND_TO_CALCULATE_1': 'TRUE',
            'REFRESH': '0',
            'LANGUAGE': 'CN',
            'SITE': 'CXRECXRE',
            'TRIP_FLOW': 'YES',
            'SKIN': 'CX',
            'EXTERNAL_ID': external_id,
            'COUNTRY': 'CN',
            'FROM_SITE': 'CX',
            'B_LOCATION_2': '', # 单程
            'B_LOCATION_1': begin_location,
            'E_LOCATION_2': '', # 单程
            'E_LOCATION_1': end_location,
            'B_DATE_1': begin_date + '0000',
            'TRAVELLER_TYPE_1': 'ADT',
            'HAS_INFANT_1': '',
            'TRAVELLER_TYPE_2': '',
            'HAS_INFANT_2': '',
            'TRAVELLER_TYPE_3': '',
            'HAS_INFANT_3': '',
            'TRAVELLER_TYPE_4': '',
            'HAS_INFANT_4': '',
            'TRAVELLER_TYPE_5': '',
            'HAS_INFANT_5': '',
            'TRAVELLER_TYPE_6': '',
            'HAS_INFANT_6': '',
            'TRAVELLER_TYPE_7': '',
            'HAS_INFANT_7': '',
            'TRAVELLER_TYPE_8': '',
            'HAS_INFANT_8': '',
            'TRAVELLER_TYPE_9': '',
            'HAS_INFANT_9': '',
            'TRIP_TYPE': 'O', # 单程
            'COMMERCIAL_FARE_FAMILY_1': 'CFFECO',
            'COMMERCIAL_FARE_FAMILY_2': 'CFFPEY',
            'COMMERCIAL_FARE_FAMILY_3': '',
            'DIRECT_NON_STOP': '',
            'PRICING_TYPE': 'O',
            'DISPLAY_TYPE': '2',
            'WDS_METHODS_OF_PAYMENT': 'CREDITCARD',
            'WDS_METHODS_OF_DELIVERY': 'ETCKT',
            'WDS_MOD_DESC_AIRL': '',
            'WDS_MOD_DESC_DELIV': '',
            'WDS_MOD_DESC_ETCKT': 'e-Ticket',
            'WDS_MOD_DESC_HAND': '',
            'WDS_MOD_DESC_PICK': '',
            'WDS_INCLUDE_TAX': 'TRUE',
            'WDS_PROPOSE_UPSELL': 'TRUE',
            'WDS_NEXT_CABIN': '',
            'WDS_FROM_CALENDAR': 'TRUE',
            'FIRST_PAGE': 'OWUP',
            'PROMO_CODE': '',
            'WDS_DATE': begin_date + "0000", # 单程
            'DOWNSELL_CFF': '',
        }

        response = send_request(session, cookies, params, data)

        res = response.json()
        reco_flight_mapping = parse_mapping(res)
        for flight in parse_flights(res, reco_flight_mapping):
            print(flight)
    
    except Exception as e:
        print(f"发生错误: {e}")

if __name__ == "__main__":
    begin_location = input("请输入出发地：")
    end_location = input("请输入目的地：")
    begin_date = input("请输入出发时间（格式 YYYYMMDD）：") 
    
    input_and_search(begin_location, end_location, begin_date)
