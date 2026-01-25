import json
import re
import os
import datetime
import time
import random
import pandas as pd
from playwright.sync_api import sync_playwright

# ================= 🔧 路径配置 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
BLOG_POST_PATH = os.path.join(PROJECT_ROOT, 'src', 'content', 'posts', 'memory-monitor.mdx')
DATA_DIR = os.path.join(CURRENT_DIR, 'data_storage')
RAW_FILE = os.path.join(DATA_DIR, 'jd_memory_raw.csv')
TREND_FILE = os.path.join(DATA_DIR, 'jd_memory_trend.csv')

os.makedirs(DATA_DIR, exist_ok=True)
TODAY = datetime.date.today().strftime('%Y-%m-%d')

print(f"📂 路径检查:\n- 脚本: {CURRENT_DIR}\n- 博客: {BLOG_POST_PATH}")

# ================= 🕷️ 爬虫部分 (Playwright 版) =================
def crawl_jd_data():
    print(f"[{TODAY}] 哀酱正在启动 Playwright (Chromium)，准备抓取数据...")
    captured_data = []

    # 定义数据包捕获的回调函数
    def handle_response(response):
        # 筛选包含京东商品数据的接口 (appid=search-pc-java)
        if "appid=search-pc-java" in response.url and response.status == 200:
            try:
                # 有些响应可能是 JSONP 或字符串，做个简单清洗
                text = response.text()
                if text.strip().startswith('jQuery') or text.strip().endswith(')'):
                    text = text[text.find('{'):text.rfind('}')+1]
                
                json_data = json.loads(text)
                
                if isinstance(json_data, dict) and "data" in json_data and "wareList" in json_data["data"]:
                    count = 0
                    for item in json_data["data"]["wareList"]:
                        title = item.get('wareName', '')
                        price = item.get('realPrice', '0')
                        link = f"https://item.jd.com/{item.get('wareId')}.html"
                        clean_title = re.sub('<.*?>', '', title)
                        
                        captured_data.append({
                            'date': TODAY, 'title': clean_title, 'price': price, 'link': link
                        })
                        count += 1
                    # print(f"  ⚡ 捕获到数据包，含 {count} 条商品")
            except Exception as e:
                pass # 解析失败就算了，别打断主流程

    with sync_playwright() as p:
        # 启动浏览器 (headless=True 是默认的，适合服务器)
        browser = p.chromium.launch(headless=True)
        # 创建上下文，伪装 User-Agent 防止被秒封
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # 开启监听：每当有响应时，触发 handle_response
        page.on("response", handle_response)

        try:
            print("正在访问京东搜索页...")
            page.goto("https://search.jd.com/Search?keyword=%E5%86%85%E5%AD%98%E6%9D%A1&enc=utf-8&wq=neicunt", timeout=60000)
            
            target_pages = 10
            for i in range(1, target_pages + 1):
                print(f"\n--- 正在处理第 {i}/{target_pages} 页 ---")
                
                # [动作 1] 滚动到底部触发懒加载
                # 使用 JS 滚动，更顺滑
                print("正在滚动页面...")
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                
                # 等待 2-4 秒让数据加载
                sleep_time = random.uniform(2, 4)
                time.sleep(sleep_time)
                
                # [动作 2] 翻页
                if i < target_pages:
                    # 定位下一页按钮
                    next_btn = page.locator("text=下一页")
                    if next_btn.is_visible():
                        print("点击下一页...")
                        next_btn.click()
                        # 翻页后必须休息，等待新页面加载
                        page.wait_for_timeout(random.randint(2000, 4000)) 
                    else:
                        print("❌ 未找到下一页按钮，提前结束。")
                        break
                        
        except Exception as e:
            print(f"❌ 爬取过程中断: {e}")
        finally:
            browser.close()

    print(f"\n🎉 全部抓取结束，共捕获 {len(captured_data)} 条数据。")
    return captured_data

# ================= 🧹 数据清洗 (保持不变) =================
def process_data(raw_data):
    if not raw_data: return None
    df = pd.DataFrame(raw_data)
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df.dropna(subset=['price'], inplace=True)

    def get_info(row):
        title = row['title'].upper()
        cap_match = re.search(r'(\d+)\s*G[B]?', title, re.IGNORECASE)
        capacity = int(cap_match.group(1)) if cap_match else 0
        
        if 'DDR5' in title: gen = 'DDR5'
        elif 'DDR4' in title: gen = 'DDR4'
        else: gen = '其他'

        if any(x in title for x in ['服务器', 'ECC', 'REG']): dev = '服务器'
        elif '笔记本' in title: dev = '笔记本'
        else: dev = '台式'
        
        return f"{dev}-{gen}", dev, capacity

    df['category'], df['device_type'], df['capacity'] = zip(*df.apply(get_info, axis=1))
    return df

# ================= 💾 智能存储 (保持不变) =================
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

# ================= 📝 博客生成 (保持不变) =================
def generate_blog(df_trend, df_raw_all):
    df_today_raw = df_raw_all[df_raw_all['date'] == TODAY]
    if df_today_raw.empty: return

    pivot_df = df_trend.pivot_table(index='date', columns='category', values='price', aggfunc='mean').round(1)
    if not pivot_df.empty:
        dates = pivot_df.index.tolist()
        series = [{"name": c, "type": "line", "smooth": True, "data": pivot_df[c].tolist()} for c in pivot_df.columns]
    else:
        dates, series = [], []

    json_dates = json.dumps(dates, ensure_ascii=False)
    json_series = json.dumps(series, ensure_ascii=False)
    json_legends = json.dumps(pivot_df.columns.tolist(), ensure_ascii=False)

    js_logic = f"""
      document.addEventListener('DOMContentLoaded', function () {{
        var chartDom = document.getElementById('main-chart');
        if (!chartDom) return;
        var myChart = echarts.init(chartDom);
        var option = {{
          title: {{ text: '内存条均价历史走势', left: 'center' }},
          tooltip: {{ trigger: 'axis' }},
          legend: {{ data: {json_legends}, bottom: 0 }},
          grid: {{ left: '3%', right: '4%', bottom: '10%', containLabel: true }},
          xAxis: {{ type: 'category', boundaryGap: false, data: {json_dates} }},
          yAxis: {{ type: 'value', name: '价格 (元)' }},
          series: {json_series}
        }};
        myChart.setOption(option);
        window.addEventListener('resize', function() {{ myChart.resize(); }});
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
                    color = "text-red-500" if pct > 0 else "text-green-500"
                    icon = "📈" if pct > 0 else "📉"
                    if abs(pct) < 0.1: trend_str = "<span class='text-gray-400'>(➖)</span>"
                    else: trend_str = f"<span class='{color}'>({icon} {pct:.1f}%)</span>"
            val = f"¥{today_p:.1f}" if not pd.isna(today_p) else "无数据"
            overview_md += f"- **{cap}G**: {val} {trend_str}\n"
        overview_md += "\n"

    mdx_content = f"""---
title: "京东内存条价格日报 ({TODAY})"
description: "DDR4/DDR5 内存条价格监控，含 16G/32G/64G 分规格均价分析。"
published: "{TODAY}"
tags: ["爬虫"]
category: "价格日报"
---

## 📊 规格均价概览

> **统计时间**: {TODAY} | **对比**: {yesterday or '无'}

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
        title = row['title'].replace('|', ' ').replace('[', '').replace(']', '')
        spec = f"{row['category']}/{row['capacity']}G"
        mdx_content += f"| {i+1} | [{title}]({row['link']}) | {spec} | **¥{row['price']}** |\n"
    
    mdx_content += "\n\n*Generated by Haibara Ai (Ver. Playwright)*"

    with open(BLOG_POST_PATH, 'w', encoding='utf-8') as f:
        f.write(mdx_content)
    print(f"✅ 博客已生成: {BLOG_POST_PATH}")

if __name__ == "__main__":
    data = crawl_jd_data()
    if data:
        df_processed = process_data(data)
        trend, raw = smart_save(df_processed)
        generate_blog(trend, raw)
    else:
        print("⚠️ 今天没爬到数据")