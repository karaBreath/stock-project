"""
universe.py — รายชื่อหุ้นทั้งหมดที่ใช้ใน Screener

หุ้นไทย (SET): ~300 ตัว ครอบคลุมทุกกลุ่มอุตสาหกรรม
หุ้นสหรัฐ: S&P 500 + NASDAQ 100 ~550 ตัว
"""
import requests
from database import cache_get, cache_set

# ─────────────────────────────────────────────
# หุ้นไทย (SET/mai) — จัดตามกลุ่มอุตสาหกรรม
# ─────────────────────────────────────────────
TH_UNIVERSE = [t + ".BK" for t in [
    # พลังงาน
    "PTT","PTTEP","PTTGC","TOP","IRPC","BCP","ESSO","SPRC","PTTAR","BBGI","SUSCO",
    # ธนาคาร
    "KBANK","SCB","BBL","KTB","BAY","TMB","TISCO","KKP","TCAP","LHBANK","CIMBT",
    "UOBT","TBANK","THANI","MTC","SAWAD","TIDLOR","AEON","KTC","ASK","SINGER",
    # ประกัน
    "BLA","MUANGTHAI","TQM","OFM","SAM","NKI","ERGO","SIAM","TVI",
    # อสังหาริมทรัพย์
    "LH","AP","SPALI","SANSIRI","QH","NOBLE","ORI","ORIGIN","COUNTRY","GRAND",
    "PRUKSA","AMATA","LALIN","SC","SUPALAI","MJD","RICHY","CHEWATHAI","LPN",
    "NPPD","SREIT","FTREIT","TPRIME","LHPF","M-STOR","AIMIRT","GGFLEX",
    # ก่อสร้าง
    "CK","ITD","STEC","NWR","SYNTEC","SEAFCO","UNIQ","PYLON","SQ","TRC","STECON",
    # ค้าปลีก/พาณิชย์
    "CPALL","MAKRO","BJC","HMPRO","ROBINS","COM7","DOHOME","TNP","BEAUTY","JMART",
    "JMT","ADVICE","SYNEX","GLOBAL","SSSC","DCC","BIG","SPCG","INET",
    # อาหารและเครื่องดื่ม
    "CPF","TU","GFPT","MINT","SFP","KSL","KTIS","PRG","SNP","M","TIPCO",
    "TFG","SAPPE","OSP","CBG","NRF","ASIAN","ICHI","SMILE","RBF","AAI",
    "SORCON","UVAN","KASET","FSS","FPT","YUASA","UHT","PM","SFOODS",
    # สุขภาพ/โรงพยาบาล
    "BDMS","BH","BCH","CHG","NTV","VIBHA","RAM","RJH","WIN","SVH",
    "LPH","SAMTEL","AI","PRARAM9","M-CHAI","WPH","PRIME","AHC",
    # โทรคมนาคม
    "ADVANC","TRUE","INTUCH","JASMINE","JAS","THCOM","CSL","INET",
    # สื่อและบันเทิง
    "WORK","BEC","MCOT","MAJOR","SF","RS","GRAMMY","MACO","VGI","PLANB",
    # ขนส่ง/โลจิสติกส์
    "AOT","AAV","BA","NOK","THAI","BTS","BEM","BECL","WICE","LEO",
    "RCL","PSL","TTA","SHIP","SITHAI","NCL","BTNC","KCE","SMART",
    # พลังงานทดแทน
    "GULF","GPSC","EGCO","RATCH","EA","BCPG","BGRIM","GUNKUL","SUPER",
    "SENA","TPCH","TPIPP","EASTW","MWG","MEGA","SUSCO","GEC","BKH",
    # อุตสาหกรรม/วัสดุ
    "SCC","SCGP","TUF","TASCO","SMPC","MASTER","KCE","HCD","PCSGH","TPC",
    "TASCO","IRC","SAT","AH","STANLY","GENCO","LRH","STA","PDI","ROJNA",
    "AMATA","HANA","DELTA","KCE","NFC","NPC","TPOLY","TCMC","TRT",
    # เทคโนโลยี
    "GULF","INSET","MFEC","CSP","JIB","BE8","2S","NETBAY","ITMX","ETDA",
    # เกษตร
    "TVO","SFLEX","SPCG","KASET","SORCON","PRG","KSL","KTIS","TFG","CPF",
    # ขนาดกลาง/เล็ก (mai)
    "SOLAR","ASAP","CAFE","BEAUTY","JMART","SE","FLOYD","MOONG","ABC",
    "EVER","SAPPE","BTNC","ITEL","BRR","EKH","HOTPOT","K","KBS",
    "KOOL","MBK","MIDA","MIT","MOONG","MVP","MWG","NAT","OCC",
    "PATO","PCT","PG","PHOL","PJW","PKN","PPM","PREB","PSH",
]]

# กรองซ้ำ
TH_UNIVERSE = list(dict.fromkeys(TH_UNIVERSE))


# ─────────────────────────────────────────────
# หุ้นสหรัฐ — S&P 500 + NASDAQ 100
# ─────────────────────────────────────────────
SP500_STATIC = [
    # Technology
    "AAPL","MSFT","NVDA","GOOGL","GOOG","META","AVGO","ORCL","CSCO","IBM",
    "INTC","AMD","QCOM","TXN","MU","AMAT","LRCX","KLAC","ADI","MCHP",
    "NXPI","SWKS","QRVO","MPWR","ENPH","SEDG","FSLR","FTNT","PANW","CRWD",
    "ZS","OKTA","NET","DDOG","SNOW","MDB","TEAM","NOW","CRM","ADBE",
    "INTU","ANSS","CDNS","SNPS","FICO","ROP","PTC","EPAM","CTSH","INFY",
    "WIT","ACN","LDOS","SAIC","BAH","CACI","PLTR","GTLB","PATH","UI",
    # Financials
    "BRK-B","JPM","V","MA","BAC","WFC","MS","GS","BLK","SPGI",
    "MCO","ICE","CME","CBOE","NDAQ","FDS","MSCI","VRSK","BR","FIS",
    "FISV","GPN","AXP","DFS","SYF","COF","ALLY","CACC","NMIH","MTG",
    "RDN","ESNT","BXMT","STWD","GPMT","AIG","MET","PRU","AFL","UNM",
    "TMK","GL","LNC","SFG","EQH","VOYA","PFG","RE","RNR","ALL",
    # Healthcare
    "LLY","UNH","JNJ","ABBV","MRK","TMO","ABT","DHR","BMY","AMGN",
    "GILD","BIIB","VRTX","REGN","MRNA","BNTX","PFE","CVS","CI","HUM",
    "MOH","CNC","ELV","HCA","THC","UHS","ENSG","AMED","AMEDISYS","AVEANNA",
    "IQV","IQVIA","CRL","PH","WAT","A","BIO","IDXX","MTD","HOLX",
    "DXCM","ISRG","SYK","ZBH","BSX","EW","MDT","BAX","BDX","COO",
    "TFX","TECH","ALGN","HSIC","XRAY","PDCO","PRGO","CTLT","RDUS","VTRS",
    # Consumer Discretionary
    "AMZN","TSLA","HD","MCD","NKE","LOW","TJX","BKNG","CMG","SBUX",
    "YUM","QSR","DRI","DARDEN","RRGB","WING","SHAK","BROS","JACK","TXRH",
    "BBY","TGT","COST","WMT","DG","DLTR","FIVE","BIG","OLLI","BURL",
    "ROST","TJX","GPS","URBN","PVH","RL","MOV","CPRI","TPR","RH",
    "W","ETSY","EBAY","CHWY","FTCH","RENT","CPNG","SE","MELI","MKL",
    "F","GM","STLA","TM","HMC","RIVN","LCID","GOEV","FSR","PSNY",
    # Consumer Staples
    "PG","KO","PEP","MDLZ","GIS","K","CPB","CAG","SJM","HRL",
    "MKC","SFLY","POST","BG","ADM","MOS","NTR","CF","FMC","ICL",
    "PM","MO","BTI","VGR","UVV","LO","CVET","SPB","CHD","CL",
    "KMB","EL","COTY","REVG","REV","TPX","SEIC","SCSS","FLWS","1800",
    # Energy
    "XOM","CVX","COP","EOG","SLB","MPC","VLO","PSX","OXY","DVN",
    "HAL","BKR","NOV","WHD","PUMP","PTEN","HP","PES","NE","VAL",
    "RIG","FTIV","OVV","FANG","PR","CTRA","MTDR","SM","PDCE","ESTE",
    "APA","AR","EQT","RRC","SWN","COG","CNX","GPOR","REI","KRP",
    # Industrials
    "RTX","LMT","BA","GE","HON","MMM","CAT","DE","EMR","ETN",
    "PH","ROK","AME","FTV","NDSN","GNRC","ITT","XYL","XYLEM","WTS",
    "FLOW","ESAB","GTLS","MIDD","AQUA","YORW","CWCO","SJW","AWR","AWK",
    "UPS","FDX","EXPD","CHRW","JBHT","KNX","SNDR","WERN","SAIA","ODFL",
    "XPO","GXO","ECHO","FWRD","HLXI","USX","ULH","MRTN","PTSI","CVLG",
    # Materials
    "LIN","APD","ECL","PPG","SHW","RPM","AXTA","HWKN","TREX","UFPI",
    "WY","PCH","PotlatchDeltic","RYN","CW","NUE","STLD","CMC","RS","WIRE",
    "AOS","SMG","MATX","ATI","AA","CENX","ACH","HBM","FCX","NEM",
    "NUE","CLF","MT","X","PKX","VALE","RIO","BHP","SCCO","TECK",
    # Real Estate
    "AMT","PLD","EQIX","CCI","SBAC","DLR","PSA","EXR","CUBE","LSI",
    "SPG","SKT","MAC","KIM","REG","BRX","RPAI","ROIC","WRI","SITC",
    "EQR","ESS","AVB","UDR","CPT","MAA","NNN","O","ADC","AGREE",
    "STAG","COLD","FR","TRNO","EGP","REXR","LXP","KITE","IIPR","MPW",
    # Utilities
    "NEE","DUK","SO","D","AEP","EXC","PCG","PG","SRE","XEL",
    "WEC","ES","AES","NI","CMS","ETR","PPL","FE","CNP","EVRG",
    "OGE","MGEE","OTTR","IDACORP","POR","AVA","NWE","OTTER","UTL","CWCO",
    # Communication
    "GOOGL","META","NFLX","DIS","CHTR","CMCSA","T","VZ","TMUS","LUMN",
    "CTL","WBD","PARA","FOXA","FOX","NYT","GCI","NWSA","NWS","DISCA",
    # Small/Mid caps
    "IONQ","RGTI","QBTS","ARQQ","IQM","QUBT","FORM","QTWO","SMCI","WOLF",
    "SOFI","AFRM","UPST","LC","OPEN","OFFERPAD","RDFN","ZILLOW","Z","ZG",
    "RBLX","U","MANU","NCTY","BILI","TME","HUYA","DOYU","JOYY","YY",
]

US_UNIVERSE = list(dict.fromkeys(SP500_STATIC))


def get_th_universe():
    return TH_UNIVERSE


def get_us_universe():
    """คืน list หุ้น US — ลองดึง S&P 500 จาก Wikipedia ก่อน fallback เป็น static list"""
    cached = cache_get("universe:us")
    if cached:
        return cached

    try:
        tbl = requests.get(
            "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0"},
        ).text
        # parse ticker จาก HTML table
        import re
        tickers = re.findall(r'<td><a[^>]*>([A-Z]{1,5}(?:\.[A-Z])?)</a></td>', tbl)
        # clean up
        tickers = [t.replace(".", "-") for t in tickers if t]
        if len(tickers) > 400:
            combined = list(dict.fromkeys(tickers + US_UNIVERSE))
            cache_set("universe:us", combined, 86400)  # cache 24 ชม
            return combined
    except Exception:
        pass

    return US_UNIVERSE


def get_universe(market: str) -> list:
    if market == "us":
        return get_us_universe()
    return get_th_universe()
