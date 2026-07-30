"""
พิกัดกลางของแต่ละประเทศ — ใช้แปลง "ประเทศต้นทางข่าว" จาก GDELT เป็นจุดบนลูกโลก

ทำไมต้องมี
---------
GDELT ปิด GEO 2.0 API (api/v2/geo/geo) ไปแล้ว — ยิงเข้าไปได้ HTTP 404 ทุกแบบ
(ยืนยันจากการทดสอบจริง 6 ครั้ง ทั้งแบบมี/ไม่มีพารามิเตอร์)
แต่ DOC 2.0 ArtList ยังใช้ได้ และแต่ละข่าวมีฟิลด์ sourcecountry ติดมาด้วย
จึงนับข่าวรายประเทศแล้ววางจุดที่พิกัดกลางของประเทศนั้นแทน

พิกัดเป็นค่ากลางคร่าว ๆ (ไม่ใช่เมืองหลวงเป๊ะ ๆ) พอสำหรับปักหมุดบนลูกโลก
"""

# ชื่อประเทศตามที่ GDELT ส่งมาใน sourcecountry -> (lat, lon)
COUNTRY_COORDS = {
    "United States": (39.8, -98.6), "United Kingdom": (54.0, -2.0),
    "Canada": (56.1, -106.3), "Australia": (-25.3, 133.8),
    "India": (20.6, 79.0), "China": (35.9, 104.2), "Japan": (36.2, 138.3),
    "Germany": (51.2, 10.5), "France": (46.2, 2.2), "Italy": (41.9, 12.6),
    "Spain": (40.5, -3.7), "Netherlands": (52.1, 5.3), "Belgium": (50.5, 4.5),
    "Switzerland": (46.8, 8.2), "Austria": (47.5, 14.6), "Sweden": (60.1, 18.6),
    "Norway": (60.5, 8.5), "Denmark": (56.3, 9.5), "Finland": (61.9, 25.7),
    "Poland": (51.9, 19.1), "Portugal": (39.4, -8.2), "Ireland": (53.4, -8.2),
    "Greece": (39.1, 21.8), "Czech Republic": (49.8, 15.5), "Romania": (45.9, 25.0),
    "Hungary": (47.2, 19.5), "Ukraine": (48.4, 31.2), "Russia": (61.5, 105.3),
    "Turkey": (39.0, 35.2), "Israel": (31.0, 34.9), "Palestine": (31.9, 35.2),
    "Saudi Arabia": (23.9, 45.1), "United Arab Emirates": (23.4, 53.8),
    "Qatar": (25.4, 51.2), "Kuwait": (29.3, 47.5), "Iran": (32.4, 53.7),
    "Iraq": (33.2, 43.7), "Syria": (34.8, 39.0), "Lebanon": (33.9, 35.9),
    "Jordan": (30.6, 36.2), "Egypt": (26.8, 30.8), "Libya": (26.3, 17.2),
    "Algeria": (28.0, 1.7), "Morocco": (31.8, -7.1), "Tunisia": (33.9, 9.5),
    "Nigeria": (9.1, 8.7), "Ghana": (7.9, -1.0), "Kenya": (-0.0, 37.9),
    "Ethiopia": (9.1, 40.5), "South Africa": (-30.6, 22.9), "Tanzania": (-6.4, 34.9),
    "Uganda": (1.4, 32.3), "Zimbabwe": (-19.0, 29.2), "Zambia": (-13.1, 27.8),
    "Sudan": (12.9, 30.2), "Somalia": (5.2, 46.2), "Senegal": (14.5, -14.5),
    "Thailand": (15.9, 100.99), "Vietnam": (14.1, 108.3), "Malaysia": (4.2, 101.98),
    "Singapore": (1.35, 103.8), "Indonesia": (-0.8, 113.9), "Philippines": (12.9, 121.8),
    "Myanmar": (21.9, 96.0), "Cambodia": (12.6, 104.99), "Laos": (19.9, 102.5),
    "South Korea": (35.9, 127.8), "North Korea": (40.3, 127.5), "Taiwan": (23.7, 121.0),
    "Hong Kong": (22.3, 114.2), "Macau": (22.2, 113.5), "Mongolia": (46.9, 103.8),
    "Pakistan": (30.4, 69.3), "Bangladesh": (23.7, 90.4), "Sri Lanka": (7.9, 80.8),
    "Nepal": (28.4, 84.1), "Afghanistan": (33.9, 67.7), "Kazakhstan": (48.0, 66.9),
    "Uzbekistan": (41.4, 64.6), "Azerbaijan": (40.1, 47.6), "Georgia": (42.3, 43.4),
    "Armenia": (40.1, 45.0), "New Zealand": (-40.9, 174.9), "Fiji": (-17.7, 178.1),
    "Papua New Guinea": (-6.3, 143.96),
    "Mexico": (23.6, -102.6), "Brazil": (-14.2, -51.9), "Argentina": (-38.4, -63.6),
    "Chile": (-35.7, -71.5), "Colombia": (4.6, -74.3), "Peru": (-9.2, -75.0),
    "Venezuela": (6.4, -66.6), "Ecuador": (-1.8, -78.2), "Bolivia": (-16.3, -63.6),
    "Uruguay": (-32.5, -55.8), "Paraguay": (-23.4, -58.4), "Cuba": (21.5, -77.8),
    "Jamaica": (18.1, -77.3), "Haiti": (19.0, -72.3), "Panama": (8.5, -80.8),
    "Costa Rica": (9.7, -83.8), "Guatemala": (15.8, -90.2), "Honduras": (15.2, -86.2),
    "Dominican Republic": (18.7, -70.2), "Puerto Rico": (18.2, -66.6),
    "Bulgaria": (42.7, 25.5), "Serbia": (44.0, 21.0), "Croatia": (45.1, 15.2),
    "Slovakia": (48.7, 19.7), "Slovenia": (46.2, 14.99), "Lithuania": (55.2, 23.9),
    "Latvia": (56.9, 24.6), "Estonia": (58.6, 25.0), "Belarus": (53.7, 27.95),
    "Iceland": (65.0, -18.6), "Luxembourg": (49.8, 6.1), "Malta": (35.9, 14.4),
    "Cyprus": (35.1, 33.4), "Albania": (41.2, 20.2), "Bosnia and Herzegovina": (43.9, 17.7),
    "Moldova": (47.4, 28.4), "Oman": (21.5, 55.9), "Bahrain": (26.0, 50.6),
    "Yemen": (15.6, 48.5), "Angola": (-11.2, 17.9), "Mozambique": (-18.7, 35.5),
    "Cameroon": (7.4, 12.4), "Ivory Coast": (7.5, -5.5), "Mali": (17.6, -4.0),
    "Niger": (17.6, 8.1), "Chad": (15.5, 18.7), "Congo": (-0.2, 15.8),
    "Rwanda": (-1.9, 29.9), "Botswana": (-22.3, 24.7), "Namibia": (-22.96, 18.5),
    "Madagascar": (-18.8, 46.9), "Mauritius": (-20.3, 57.6),
}

# ชื่อที่ GDELT สะกดต่างจากตารางหลัก
ALIASES = {
    "USA": "United States", "US": "United States", "UK": "United Kingdom",
    "Republic of Korea": "South Korea", "Korea": "South Korea",
    "Viet Nam": "Vietnam", "Russian Federation": "Russia",
    "Cote d'Ivoire": "Ivory Coast", "Czechia": "Czech Republic",
    "Burma": "Myanmar", "UAE": "United Arab Emirates",
    "Democratic Republic of the Congo": "Congo", "Republic of the Congo": "Congo",
    "Bosnia": "Bosnia and Herzegovina", "Holland": "Netherlands",
}


def coords_for(country: str):
    """คืน (lat, lon) ของประเทศ หรือ None ถ้าไม่รู้จัก"""
    if not country:
        return None
    name = country.strip()
    if name in COUNTRY_COORDS:
        return COUNTRY_COORDS[name]
    alias = ALIASES.get(name)
    if alias:
        return COUNTRY_COORDS.get(alias)
    return None


def known_count() -> int:
    return len(COUNTRY_COORDS)
