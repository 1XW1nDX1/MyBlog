import json
import csv
import re
import os
import datetime
import time
import random
import pandas as pd
from DrissionPage import ChromiumPage, ChromiumOptions

# ================= 🔧 路径配置 (已适配你的本地环境) =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
BLOG_POST_PATH = os.path.join(PROJECT_ROOT, 'src', 'content', 'posts', 'memory-monitor.mdx')
DATA_DIR = os.path.join(CURRENT_DIR, 'data_storage')
RAW_FILE = os.path.join(DATA_DIR, 'jd_memory_raw.csv')
TREND_FILE = os.path.join(DATA_DIR, 'jd_memory_trend.csv')

os.makedirs(DATA_DIR, exist_ok=True)
TODAY = datetime.date.today().strftime('%Y-%m-%d')

# ================= 🕷️ 爬虫部分 (本地运行版) =================
def crawl_jd_data():
    print(f"[{TODAY}] 哀酱正在准备启动浏览器...")
    
    co = ChromiumOptions()
    # 在本地运行建议关闭无头模式(headless)，这样你可以亲眼看着它工作
    # 如果你嫌烦，可以改成 co.headless(True)
    co.headless(False) 
    
    co.set_argument('--no-sandbox')
    co.set_argument('--disable-gpu')
    co.set_argument('--window-size=1920,1080')
        
    # 实例化浏览器 (会自动寻找你电脑里的 Edge 或 Chrome)
    edge = ChromiumPage(co)
        
    # 如果你在环境变量里设置过 JD_COOKIE 就用它，没有就“裸奔”
    jd_cookie = os.getenv('JD_COOKIE') 
    
    if jd_cookie:
        print("🍪 正在注入你的 Cookie...")
        cookie_list = []
        for item in jd_cookie.split(';'):
            if '=' in item:
                k, v = item.split('=', 1)
                cookie_list.append({'name': k.strip(), 'value': v.strip(), 'domain': '.jd.com'})
        edge.set.cookies(cookie_list)
    else:
        print("⚠️ 未检测到 Cookie，可能会触发京东的验证码哦，你要盯着点。")

    captured_data = []

    try:
        # 启动监听
        edge.listen.start("?appid=search-pc-java&t=")
        print("正在访问京东搜索页...")
        edge.get("https://search.jd.com/Search?keyword=%E5%86%85%E5%AD%98%E6%9D%A1&enc=utf-8&wq=neicunt")
            
        target_pages = 10
        for page in range(1, target_pages + 1):
            print(f"\n--- 正在处理第 {page}/{target_pages} 页 ---")
            
            # 滚动页面确保元素加载
            next_p = edge.ele('text=下一页')
            edge.scroll.to_see(next_p)
            
            # 等待数据包
            resp_list = edge.listen.wait(count=5, timeout=60)
            
            if isinstance(resp_list, bool):
                print(f"⚠️ 第 {page} 页等待超时。")
                resp_list = []

            page_count = 0
            for resp in resp_list:
                raw_body = resp.response.body
                if isinstance(raw_body, str):
                    try:
                        if raw_body.strip().startswith('jQuery') or raw_body.strip().endswith(')'):
                            raw_body = raw_body[raw_body.find('{'):raw_body.rfind('}')+1]
                        json_data = json.loads(raw_body)
                    except: continue
                else:
                    json_data = raw_body

                if isinstance(json_data, dict) and "data" in json_data and "wareList" in json_data["data"]:
                    for item in json_data["data"]["wareList"]:
                        title = item.get('wareName', '')
                        price = item.get('realPrice', '0')
                        link = f"https://item.jd.com/{item.get('wareId')}.html"
                        clean_title = re.sub('<.*?>', '', title)
                        
                        captured_data.append({
                            'date': TODAY, 'title': clean_title, 'price': price, 'link': link
                        })
                        page_count += 1
            
            print(f"✅ 第 {page} 页捕获 {page_count} 条。")

            if page < target_pages:
                next_btn = edge.ele('text=下一页')
                if next_btn:
                    next_btn.click() 
                    time.sleep(random.uniform(2, 5))
                else:
                    break
                
    except Exception as e:
        print(f"❌ 运行报错了: {e}")
        edge.get_screenshot(path=os.path.join(DATA_DIR, 'error_screenshot.png'))
        raise e
    finally:
        edge.quit()

    return captured_data

# ================= 🧹 数据清洗 =================
def process_data(raw_data):
    if not raw_data: return None
    df = pd.DataFrame(raw_data)
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df.dropna(subset=['price'], inplace=True)

    def get_info(row):
        title = row['title'].upper()
        cap_match = re.search(r'(\d+)\s*G[B]?', title, re.IGNORECASE)
        capacity = int(cap_match.group(1)) if cap_match else 0
        gen = 'DDR5' if 'DDR5' in title else ('DDR4' if 'DDR4' in title else '其他')
        dev = '服务器' if any(x in title for x in ['服务器', 'ECC', 'REG']) else ('笔记本' if '笔记本' in title else '台式')
        return f"{dev}-{gen}", dev, capacity

    df['category'], df['device_type'], df['capacity'] = zip(*df.apply(get_info, axis=1))
    return df

# ================= 💾 存储逻辑 =================
def smart_save(df_today):
    daily_summary = df_today.groupby(['date', 'category'])['price'].mean().round(1).reset_index()
    if os.path.exists(TREND_FILE):
        df_trend = pd.read_csv(TREND_FILE)
        df_trend = df_trend[df_trend['date'] != TODAY]
        df_trend = pd.concat([df_trend, daily_summary], ignore_index=True)
    else:
        df_trend = daily_summary
    df_trend.to_csv(TREND_FILE, index=False)

    if os.path.exists(RAW_FILE):
        df_raw_old = pd.read_csv(RAW_FILE)
        df_raw_old = df_raw_old[df_raw_old['date'] != TODAY]
        df_raw_all = pd.concat([df_raw_old, df_today], ignore_index=True)
    else:
        df_raw_all = df_today

    unique_dates = sorted(df_raw_all['date'].unique())
    if len(unique_dates) > 3:
        df_raw_all = df_raw_all[df_raw_all['date'].isin(unique_dates[-3:])]
    
    df_raw_all.to_csv(RAW_FILE, index=False)
    return df_trend, df_raw_all

# ================= 📝 博客生成 =================
def generate_blog(df_trend, df_raw_all):
    df_today_raw = df_raw_all[df_raw_all['date'] == TODAY]
    if df_today_raw.empty: return

    pivot_df = df_trend.pivot_table(index='date', columns='category', values='price', aggfunc='mean').round(1)
    dates = pivot_df.index.tolist() if not pivot_df.empty else []
    series = [{"name": c, "type": "line", "smooth": True, "data": pivot_df[c].tolist()} for c in pivot_df.columns] if not pivot_df.empty else []

    js_logic = f"""
      document.addEventListener('DOMContentLoaded', function () {{
        var chartDom = document.getElementById('main-chart');
        if (!chartDom) return;
        var myChart = echarts.init(chartDom);
        myChart.setOption({{
          title: {{ text: '内存条均价历史走势', left: 'center' }},
          tooltip: {{ trigger: 'axis' }},
          legend: {{ data: {json.dumps(pivot_df.columns.tolist() if not pivot_df.empty else [])}, bottom: 0 }},
          xAxis: {{ type: 'category', boundaryGap: false, data: {json.dumps(dates)} }},
          yAxis: {{ type: 'value', name: '价格 (元)' }},
          series: {json.dumps(series)}
        }});
      }});
    """

    specs = {'笔记本': [16, 32], '台式': [16, 32, 64], '服务器': [32, 64, 128]}
    dates_raw = sorted(df_raw_all['date'].unique())
    yesterday = dates_raw[-2] if len(dates_raw) >= 2 else None
    
    overview_md = ""
    for dev, caps in specs.items():
        overview_md += f"### {dev}内存\n"
        df_dev = df_raw_all[df_raw_all['device_type'] == dev]
        for cap in caps:
            df_target = df_dev[df_dev['capacity'] == cap]
            today_p = df_target[df_target['date'] == TODAY]['price'].mean()
            trend_str = ""
            if not pd.isna(today_p) and yesterday:
                prev_p = df_target[df_target['date'] == yesterday]['price'].mean()
                if not pd.isna(prev_p) and prev_p > 0:
                    pct = ((today_p - prev_p) / prev_p) * 100
                    icon = "📈" if pct > 0 else "📉"
                    color = "text-red-500" if pct > 0 else "text-green-500"
                    trend_str = f"<span class='{color}'>({icon} {pct:.1f}%)</span>"
            val = f"¥{today_p:.1f}" if not pd.isna(today_p) else "无数据"
            overview_md += f"- **{cap}G**: {val} {trend_str}\n"
        overview_md += "\n"

    mdx_content = f"""---
title: "京东内存条价格日报 ({TODAY})"
published: "{TODAY}"
tags: ["爬虫"]
category: "价格日报"
---

## 📊 规格均价概览
{overview_md}

## 📈 历史趋势
<div id="main-chart" style="width: 100%; height: 400px;"></div>
<script is:inline src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<script is:inline set:html={{`{js_logic}`}}></script>

## 📋 最低价榜单
| 排名 | 商品 | 规格 | 价格 |
| :--- | :--- | :--- | :--- |
"""
    top3 = df_today_raw.sort_values('price').head(3)
    for i, (_, row) in enumerate(top3.iterrows()):
        mdx_content += f"| {i+1} | [{row['title']}]({row['link']}) | {row['category']}/{row['capacity']}G | **¥{row['price']}** |\n"
    
    with open(BLOG_POST_PATH, 'w', encoding='utf-8') as f:
        f.write(mdx_content)
    print(f"✅ 任务完成。博客已生成在: {BLOG_POST_PATH}")

if __name__ == "__main__":
    data = crawl_jd_data()
    if data:
        df_processed = process_data(data)
        trend, raw = smart_save(df_processed)
        generate_blog(trend, raw)
    else:
        print("⚠️ 颗粒无收，去检查下你的网络或者 Cookie 吧。")