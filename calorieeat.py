import streamlit as st
import requests
import urllib3
import pandas as pd
from bs4 import BeautifulSoup
from urllib.parse import quote
import os
import re
from deep_translator import GoogleTranslator
from config import USDA_API_KEY

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

if not USDA_API_KEY:
    st.error("USDA API KEY가 설정되어 있지 않습니다. 환경변수 USDA_API_KEY를 확인하세요.")

def parse_measurement(s: str):
    match = re.search(r"([\d\.]+)\s*([a-zA-Z]+)", s)
    if match:
        try:
            qty = float(match.group(1))
        except Exception:
            qty = None
        unit = match.group(2).lower()
        return qty, unit
    return None, None

@st.cache_data(show_spinner=False)
def load_fooddb():
    path_abs = r"C:\Users\USER\hw1\음식DB.csv"
    if os.path.exists(path_abs):
         return pd.read_csv(path_abs)
    else:
         return pd.read_csv("음식DB.csv")

@st.cache_data(show_spinner=False)
def get_food_options():
    df = load_fooddb()
    if df.empty:
        return []
    options = df["식품명"].dropna().unique().tolist()
    options = sorted(options, key=lambda x: x.lower())
    return options

@st.cache_data(show_spinner=False)
def load_nutrition_data():
    filename1 = r"농촌진흥청_국립식량과학원_통합식품영양성분정보(원재료성식품)_20250224.csv"
    filename2 = r"해양수산부_국립수산과학원_통합식품영양성분정보(원재료성식품)_20250113.csv"
    dfs = []
    if os.path.exists(filename1):
        try:
            df1 = pd.read_csv(filename1, encoding="utf-8")
            dfs.append(df1)
        except Exception as e:
            st.error(f"농촌진흥청 데이터 로딩 중 오류: {e}")
    if os.path.exists(filename2):
        try:
            df2 = pd.read_csv(filename2, encoding="utf-8")
            dfs.append(df2)
        except Exception as e:
            st.error(f"해양수산부 데이터 로딩 중 오류: {e}")
    if dfs:
        return pd.concat(dfs, ignore_index=True)
    else:
        st.error("영양성분 데이터 파일들을 찾을 수 없습니다.")
        return pd.DataFrame()

def get_usda_calorie_info(ingredient):
    try:
        translated = GoogleTranslator(source='ko', target='en').translate(ingredient)
    except Exception as e:
        st.error("번역 에러: " + str(e))
        return None, None
    search_url = f"https://api.nal.usda.gov/fdc/v1/foods/search?query={quote(translated)}&pageSize=1&api_key={USDA_API_KEY}"
    try:
        r = requests.get(search_url)
        data = r.json()
    except Exception as e:
        st.error("USDA API 호출 에러: " + str(e))
        return None, None
    if "foods" in data and len(data["foods"]) > 0:
        food = data["foods"][0]
        calorie = None
        for nutrient in food.get("foodNutrients", []):
            nutrient_name = nutrient.get("nutrient", {}).get("name", "").lower()
            if "energy" in nutrient_name:
                calorie = nutrient.get("value")
                break
        if calorie is not None:
            return "100g", calorie
    return None, None

def get_calorie_info(ingredient, nutrition_df):
    ingredient_lower = ingredient.lower()
    exact_mask = (nutrition_df["식품명"].str.lower() == ingredient_lower) | \
                 (nutrition_df["대표식품명"].str.lower() == ingredient_lower) | \
                 (nutrition_df["식품중분류명"].str.lower() == ingredient_lower)
    if exact_mask.sum() > 0:
        match = nutrition_df[exact_mask].iloc[0]
        serving = match["영양성분함량기준량"]
        energy = match["에너지(kcal)"]
        return serving, energy
    partial_mask = nutrition_df["식품명"].str.contains(ingredient, case=False, na=False) | \
                    nutrition_df["대표식품명"].str.contains(ingredient, case=False, na=False) | \
                    nutrition_df["식품중분류명"].str.contains(ingredient, case=False, na=False)
    if partial_mask.sum() > 0:
        match = nutrition_df[partial_mask].iloc[0]
        serving = match["영양성분함량기준량"]
        energy = match["에너지(kcal)"]
        return serving, energy
    return get_usda_calorie_info(ingredient)

def fix_image_url(image_path: str) -> str:
    if not image_path:
        return ""
    image_path = image_path.strip()
    if image_path.startswith("http"):
        return image_path
    image_path = image_path.lstrip("/")
    if not image_path.startswith("image/"):
        image_path = "image/" + image_path
    return "https://www.semie.cooking/" + image_path

def fetch_initial_recipes(query):
    encoded_query = quote(query)
    url = f"https://www.semie.cooking/search/a/{encoded_query}"
    try:
        response = requests.get(url, verify=False)
    except Exception as e:
        st.error(f"레시피를 가져오는 중 오류: {e}")
        return [], False
    recipes = []
    show_more = False
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        result_div = soup.find("div", class_="result")
        recipe_panel = None
        if result_div:
            panels = result_div.find_all("div", class_="panel")
            for panel in panels:
                new_cont_tit = panel.find("div", class_="new-cont-tit")
                if new_cont_tit and "레시피" in new_cont_tit.get_text(strip=True):
                    recipe_panel = panel
                    break
        if not recipe_panel:
            return recipes, False
        more_button = recipe_panel.find("button", id="btnMore2")
        if more_button:
            show_more = True
        li_items = recipe_panel.find_all("li")
        for li in li_items:
            a_tag = li.find("a", href=True)
            if not a_tag:
                continue
            recipe_url = a_tag["href"]
            if recipe_url.startswith("/"):
                recipe_url = "https://www.semie.cooking" + recipe_url
            img_div = li.find("div", class_="img")
            if img_div:
                img_tag = img_div.find("img")
                image = img_tag.get("src", "") if img_tag else ""
                image = fix_image_url(image)
            else:
                image = ""
            text_div = li.find("div", class_="text")
            if text_div:
                title = text_div.find("h4").get_text(strip=True) if text_div.find("h4") else ""
                description = text_div.find("p").get_text(strip=True) if text_div.find("p") else ""
            else:
                title, description = "", ""
            ready_time, cook_time = "", ""
            tag_wrap = li.find("ul", class_="tagWrap")
            if tag_wrap:
                for time_item in tag_wrap.find_all("li"):
                    span = time_item.find("span")
                    if span:
                        label = span.get_text(strip=True)
                        value = time_item.get_text(strip=True).replace(label, "").strip()
                        if "준비시간" in label:
                            ready_time = value
                        elif "조리시간" in label:
                            cook_time = value
            recipes.append({
                "title": title,
                "description": description,
                "image": image,
                "url": recipe_url,
                "ready_time": ready_time,
                "cook_time": cook_time
            })
            if len(recipes) >= 4:
                break
    return recipes, show_more

def fetch_more_recipes(query, page=1):
    encoded_query = quote(query)
    url = f"https://www.semie.cooking/search/more?g=recipe&t=a&q={encoded_query}&p={page}"
    try:
        response = requests.get(url, verify=False)
    except Exception as e:
        st.error(f"추가 레시피 가져오는 중 오류: {e}")
        return []
    more_recipes = []
    if response.status_code == 200:
        data = response.json()
        for item in data.get("item", []):
            recipe_url = f"https://www.semie.cooking/recipe-lab/archive/{item.get('path', '')}"
            image = fix_image_url(item.get("image", ""))
            more_recipes.append({
                "title": item.get("title", ""),
                "description": item.get("intTitle", ""),
                "image": image,
                "ready_time": item.get("readyTime", ""),
                "cook_time": item.get("cookTime", ""),
                "url": recipe_url
            })
    return more_recipes

@st.cache_data(show_spinner=False)
def fetch_recipe_details(recipe_url):
    try:
        response = requests.get(recipe_url, verify=False)
    except Exception as e:
        return {}
    details = {}
    if response.status_code == 200:
        soup = BeautifulSoup(response.text, 'html.parser')
        intro = soup.find("div", class_="recipe_intro")
        if intro:
            serv_li = intro.find("i", class_="serv")
            if serv_li and serv_li.parent:
                serving = serv_li.parent.find("span").get_text(strip=True)
                details["serving"] = serving
            else:
                details["serving"] = ""
            ing_div = intro.find("div", class_="recipe_ingredient")
            ingredients = {}
            if ing_div:
                ing_blocks = ing_div.find_all("div", class_="ingredient")
                for block in ing_blocks:
                    header_p = block.find("p", class_="ingredient_h")
                    if header_p and header_p.contents:
                        category = header_p.contents[0].strip()
                    else:
                        category = "기타"
                    ing_list = []
                    ul = block.find("ul", class_="ingredient_item")
                    if ul:
                        for li in ul.find_all("li"):
                            text = li.get_text(strip=True)
                            if "(" in text and ")" in text:
                                left, right = text.split("(", 1)
                                metric = right.rstrip(")")
                                left = left.strip()
                                if " " in left:
                                    name, qty = left.rsplit(" ", 1)
                                else:
                                    name = left
                                    qty = ""
                            else:
                                name = text
                                qty = ""
                                metric = ""
                            ing_list.append({
                                "name": name,
                                "quantity": qty,
                                "metric": metric
                            })
                    ingredients[category] = ing_list
            details["ingredients"] = ingredients
    return details

def display_recipes(recipes):
    fooddb_df = load_nutrition_data()
    for rec in recipes:
        cols = st.columns([1, 2])
        with cols[0]:
            if rec["image"]:
                st.image(rec["image"], width=150)
            else:
                st.write("이미지 없음")
        with cols[1]:
            st.subheader(rec["title"])
            st.write(rec["description"])
            st.write(f"준비시간: {rec['ready_time']} / 조리시간: {rec['cook_time']}")
            st.markdown(f"[레시피 보러가기]({rec['url']})")
            with st.expander("재료 및 인분 정보 보기"):
                details = fetch_recipe_details(rec["url"])
                serving = details.get("serving", "")
                if serving:
                    st.write(f"**인분 수:** {serving}")
                ingredients = details.get("ingredients", {})
                for category, ing_list in ingredients.items():
                    st.write(f"**{category}**")
                    for ing in ing_list:
                        name = ing.get('name', '').strip()
                        quantity = ing.get('quantity', '').strip()
                        metric = ing.get('metric', '').strip()
                        if metric and (("g" in metric.lower()) or ("ml" in metric.lower())):
                            if quantity:
                                ing_text = f"{name} {quantity} ({metric})"
                            else:
                                ing_text = f"{name} ({metric})"
                        else:
                            if quantity:
                                ing_text = f"{name} {quantity}"
                            else:
                                ing_text = name
                        s_val, energy = get_calorie_info(name, fooddb_df)
                        if s_val and energy:
                            base_qty, base_unit = parse_measurement(s_val)
                            actual_qty, actual_unit = parse_measurement(metric) if metric else (None, None)
                            if base_qty is not None and actual_qty is not None and base_unit == actual_unit:
                                scaled = (actual_qty / base_qty) * energy
                                calorie_info = f"{scaled:.0f} kcal"
                            else:
                                calorie_info = f"{energy} kcal"
                            ing_text = f"{ing_text} - {calorie_info}"
                        st.write(ing_text)
                        
def apply_button_style():
    st.markdown("""
        <style>
        div.stButton > button {
            width: 120px;
            height: 60px;
            text-align: center;
            line-height: 1.2;
            white-space: pre-line;
            font-weight: bold;
            float: right;
        }
        </style>
    """, unsafe_allow_html=True)
                        

def recipe_search_page():
    apply_button_style()
    
    header_cols = st.columns([8, 2])
    with header_cols[1]:
        if st.button("칼로리\n계산하기", key="switch_to_info"):
            st.session_state.page = "info"
    query = st.text_input("검색어 입력")
    if query:
        if st.session_state.get("current_query", "") != query:
            st.session_state.current_query = query
            st.session_state.page = "search"
            recipes, show_more = fetch_initial_recipes(query)
            st.session_state.all_recipes = recipes
            st.session_state.show_more = show_more
        if st.session_state.get("all_recipes"):
            display_recipes(st.session_state.all_recipes)
        else:
            st.write("검색 결과가 없습니다.")
        if st.session_state.get("show_more", False):
            if st.button("더보기"):
                st.session_state.page += 1
                more_recipes = fetch_more_recipes(query, st.session_state.page)
                if more_recipes:
                    st.session_state.all_recipes.extend(more_recipes)
                    if len(more_recipes) < 4:
                        st.session_state.show_more = False
                else:
                    st.session_state.show_more = False

def personal_info_page():
    apply_button_style()

    if st.button("레시피\n보러가기", key="switch_to_search"):
        st.session_state.page = "search"

    st.title("내 정보 입력하기")
    st.write("본인의 하루 적정 칼로리량과 섭취 칼로리를 계산해보세요.")

    height = st.number_input("키 (cm)", min_value=100, max_value=250, value=170)
    weight = st.number_input("몸무게 (kg)", min_value=30, max_value=200, value=70)
    gender = st.selectbox("성별", options=["남", "여"])
    if gender == "남":
        recommended = weight * 35
    else:
        recommended = weight * 30

    options = get_food_options()
    fooddb_df = load_fooddb()

    st.write("---")
    st.subheader("식사별 음식 선택")

    breakfast = st.multiselect("아침", options=options, key="breakfast")
    b_cal, b_details = calculate_meal_calories(breakfast, fooddb_df)
    st.write(f"**아침 총 칼로리:** {b_cal} kcal")

    lunch = st.multiselect("점심", options=options, key="lunch")
    l_cal, l_details = calculate_meal_calories(lunch, fooddb_df)
    st.write(f"**점심 총 칼로리:** {l_cal} kcal")

    dinner = st.multiselect("저녁", options=options, key="dinner")
    d_cal, d_details = calculate_meal_calories(dinner, fooddb_df)
    st.write(f"**저녁 총 칼로리:** {d_cal} kcal")

    st.write("---")
    st.subheader("칼로리 정보 요약")
    st.write(f"추천 하루 섭취 칼로리: **{recommended:.0f} kcal**")

    total_daily = b_cal + l_cal + d_cal
    st.write(f"**하루 총 섭취 칼로리:** {total_daily} kcal")

    if total_daily > (recommended + 100):
        st.write("🚨 권장 섭취량보다 많습니다.")
    elif total_daily < (recommended - 100):
        st.write("🚨 권장 섭취량에 미치지 않습니다.")
    else:
        st.write("✅ 권장 섭취량을 충족합니다.")

def calculate_meal_calories(meal_list, df):
    total = 0
    details = []
    for food in meal_list:
        s_val, energy = get_calorie_info(food, df)
        if s_val and energy:
            total += energy
            details.append(f"{food}: {energy} kcal")
        else:
            details.append(food)
    return total, details


def main():
    if "page" not in st.session_state:
        st.session_state.page = "search"
    st.title("calorieeat")
    if st.session_state.page == "search":
        recipe_search_page()
    elif st.session_state.page == "info":
        personal_info_page()

if __name__ == "__main__":
    main()
