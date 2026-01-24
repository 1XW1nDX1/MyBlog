import json
import csv
import re
import os
import datetime
import pandas as pd
from DrissionPage import ChromiumPage, ChromiumOptions

# ================= 配置区域 =================
# Astro 博客文章路径
BLOG_POST_PATH = 'src/content/posts/memory-monitor.mdx'
DATA_DIR = 'data_storage'

# 两个数据文件：一个存短期详细数据，一个存长期均价趋势
RAW_FILE = os.path.join(DATA_DIR, 'jd_memory_raw.csv')   # 详细数据 (只留最近3天)
TREND_FILE = os.path.join(DATA_DIR, 'jd_memory_trend.csv') # 均价数据 (永久保存)

# 确保数据目录存在
os.makedirs(DATA_DIR, exist_ok=True)
TODAY = datetime.date.today().strftime('%Y-%m-%d')

# ================= 1. 爬虫部分 =================
def crawl_jd_data():
    print(f"[{TODAY}] 哀酱正在启动浏览器，准备抓取数据...")
    co = ChromiumOptions()
    co.headless()
    # co.set_argument('--no-sandbox')
    # co.set_argument('--disable-gpu')
    edge = ChromiumPage(co)

    captured_data = []

    try:
        edge.listen.start("appid=search-pc-java")
        edge.get("https://search.jd.com/Search?keyword=%E5%86%85%E5%AD%98%E6%9D%A1&enc=utf-8&wq=neicunt")
        
        print("正在滚动页面以触发懒加载...")
        edge.scroll.to_bottom()
        
        # 等待数据包
        resp_list = edge.listen.wait(count=4, timeout=60)
        if isinstance(resp_list, bool):
            print("等待超时，可能只抓到了部分数据。")
            resp_list = []

        for resp in resp_list:
            raw_body = resp.response.body
            if isinstance(raw_body, str):
                try:
                    if raw_body.strip().startswith('jQuery') or raw_body.strip().endswith(')'):
                        raw_body = raw_body[raw_body.find('{'):raw_body.rfind('}')+1]
                    json_data = json.loads(raw_body)
                except:
                    continue
            else:
                json_data = raw_body

            if isinstance(json_data, dict) and "data" in json_data and isinstance(json_data["data"], dict) and "wareList" in json_data["data"]:
                for item in json_data["data"]["wareList"]:
                    title = item.get('wareName', '')
                    price = item.get('realPrice', '0')
                    link = f"https://item.jd.com/{item.get('wareId')}.html"
                    
                    # 简单清洗 HTML 标签
                    clean_title = re.sub('<.*?>', '', title)
                    
                    captured_data.append({
                        'date': TODAY,
                        'title': clean_title,
                        'price': price,
                        'link': link
                    })
    except Exception as e:
        print(f"爬取异常: {e}")
    finally:
        edge.quit()

    return captured_data

# ================= 2. 数据处理与分类 =================
def process_data(raw_data):
    if not raw_data:
        return None

    df = pd.DataFrame(raw_data)
    df['price'] = pd.to_numeric(df['price'], errors='coerce')
    df.dropna(subset=['price'], inplace=True)

    def get_category(row):
        title = row['title'].upper()
        # 1. 代数
        if 'DDR5' in title: gen = 'DDR5'
        elif 'DDR4' in title: gen = 'DDR4'
        else: gen = '其他'
        # 2. 类型
        if any(x in title for x in ['服务器', 'ECC', 'REG']): dev = '服务器'
        elif '笔记本' in title: dev = '笔记本'
        else: dev = '台式' # 默认
        return f"{dev}-{gen}"

    df['category'] = df.apply(get_category, axis=1)
    return df

# ================= 3. 智能存储逻辑 (核心修改) =================
def smart_save(df_today):
    # --- A. 更新长期趋势文件 (Trend File) ---
    # 计算今天的各类均价
    daily_summary = df_today.groupby(['date', 'category'])['price'].mean().round(1).reset_index()
    
    # 读取旧趋势 (如果存在)
    if os.path.exists(TREND_FILE):
        df_trend = pd.read_csv(TREND_FILE)
        # 删除今天已有的记录 (防止重复运行导致重复)
        df_trend = df_trend[df_trend['date'] != TODAY]
        df_trend = pd.concat([df_trend, daily_summary], ignore_index=True)
    else:
        df_trend = daily_summary
    
    df_trend.to_csv(TREND_FILE, index=False)
    print(f"趋势数据已更新。")

    # --- B. 更新短期详细文件 (Raw File) ---
    # 策略：读取旧文件 -> 合并今天 -> 只保留最近3天
    if os.path.exists(RAW_FILE):
        df_raw_old = pd.read_csv(RAW_FILE)
        df_raw_old = df_raw_old[df_raw_old['date'] != TODAY] # 先剔除今天的旧数据
        df_raw_all = pd.concat([df_raw_old, df_today], ignore_index=True)
    else:
        df_raw_all = df_today

    # 清理过期数据
    # 获取所有唯一的日期，排序
    unique_dates = sorted(df_raw_all['date'].unique())
    # 如果超过3天，只保留最后3天
    if len(unique_dates) > 3:
        keep_dates = unique_dates[-3:]
        print(f"正在清理过期数据，只保留: {keep_dates}")
        df_raw_all = df_raw_all[df_raw_all['date'].isin(keep_dates)]
    
    df_raw_all.to_csv(RAW_FILE, index=False)
    print(f"详细数据已保存，当前存储日期范围: {df_raw_all['date'].unique()}")
    
    return df_trend, df_raw_all

# ================= 4. 博客生成 (含环比分析) =================
def generate_blog(df_trend, df_raw_today):
    if df_raw_today.empty:
        return

    # --- 1. 准备折线图数据 (来源：Trend File) ---
    # 透视表：Index=Date, Columns=Category, Values=Price
    pivot_df = df_trend.pivot_table(index='date', columns='category', values='price', aggfunc='mean').round(1)
    
    dates = pivot_df.index.tolist()
    series_data = []
    for col in pivot_df.columns:
        series_data.append({
            "name": col,
            "type": "line",
            "smooth": True,
            "data": pivot_df[col].tolist()
        })

    json_dates = json.dumps(dates, ensure_ascii=False)
    json_series = json.dumps(series_data, ensure_ascii=False)
    json_legends = json.dumps(pivot_df.columns.tolist(), ensure_ascii=False)
    
    # 构建 JS 逻辑
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

    # --- 2. 准备“均价概览”与“较昨日变化” (来源：Trend File) ---
    # 获取今天和昨天的数据
    today_summary = df_trend[df_trend['date'] == TODAY].set_index('category')['price']
    
    # 尝试找昨天（或者最近的一天）
    # 这里简单处理：找 dates 列表里 TODAY 的前一个日期
    if len(dates) >= 2 and dates[-1] == TODAY:
        yesterday_str = dates[-2]
        yesterday_summary = df_trend[df_trend['date'] == yesterday_str].set_index('category')['price']
    else:
        yesterday_summary = pd.Series()

    # 生成概览部分的 Markdown
    summary_md = ""
    for cat in today_summary.index:
        price_now = today_summary[cat]
        
        # 计算变化
        if cat in yesterday_summary:
            price_prev = yesterday_summary[cat]
            diff = price_now - price_prev
            percent = (diff / price_prev) * 100
            if diff > 0:
                trend_icon = "📈"
                trend_str = f"+{percent:.1f}%"
                color_class = "text-red-500" # 涨价一般用红（Astro可用Tailwind）
            elif diff < 0:
                trend_icon = "📉"
                trend_str = f"{percent:.1f}%"
                color_class = "text-green-500" # 跌价用绿
            else:
                trend_icon = "➖"
                trend_str = "0.0%"
                color_class = "text-gray-500"
            
            summary_md += f"- **{cat}**: ¥{price_now} <span class='{color_class}'>({trend_icon} {trend_str})</span>\n"
        else:
            summary_md += f"- **{cat}**: ¥{price_now} (🆕 新数据)\n"

    # --- 3. 生成 MDX 内容 ---
    mdx_content = f"""---
title: "京东内存条价格日报 ({TODAY})"
description: "DDR4/DDR5 内存条价格监控，含每日均价涨跌分析。"
published: "{TODAY}"
cover: ""
tags: ["爬虫"]
category: "价格日报"
---

## 📊 今日均价概览

> **数据日期**: {TODAY} | **较昨日变化**

{summary_md}

## 📈 历史价格走势

<div id="main-chart" style="width: 100%; height: 400px;"></div>
<script is:inline src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<script is:inline set:html={{`{js_logic}`}}></script>

## 📋 今日详细价格榜

### 📉 捡漏专区 (最低价 Top 3)

| 排名 | 商品 | 类别 | 价格 |
| :--- | :--- | :--- | :--- |
"""

    # --- 4. 详细榜单 (来源：Raw File 的 Today 数据) ---
    df_sorted = df_raw_today.sort_values(by='price', ascending=True)
    top3 = df_sorted.head(3)
    
    for i, (_, row) in enumerate(top3.iterrows()):
        safe_title = row['title'].replace('|', ' ').replace('[', '').replace(']', '')
        mdx_content += f"| {i+1} | [{safe_title}]({row['link']}) | {row['category']} | **¥{row['price']}** |\n"

    mdx_content += """
### 💎 土豪专区 (最高价 Top 3)

| 排名 | 商品 | 类别 | 价格 |
| :--- | :--- | :--- | :--- |
"""
    high3 = df_sorted.tail(3).iloc[::-1]
    for i, (_, row) in enumerate(high3.iterrows()):
        safe_title = row['title'].replace('|', ' ').replace('[', '').replace(']', '')
        mdx_content += f"| {i+1} | [{safe_title}]({row['link']}) | {row['category']} | ¥{row['price']} |\n"

    mdx_content += f"""
---
*Generated by Haibara Ai (Daily Monitor)*
"""

    try:
        with open(BLOG_POST_PATH, 'w', encoding='utf-8') as f:
            f.write(mdx_content)
        print(f"MDX 博客生成完毕: {BLOG_POST_PATH}")
    except Exception as e:
        print(f"写入MDX失败: {e}")

# ================= 主程序 =================
if __name__ == "__main__":
    # 1. 爬取今天的数据
    raw_data = crawl_jd_data()
    
    if raw_data:
        # 2. 处理清洗
        df_today = process_data(raw_data)
        
        # 3. 智能存储 (返回 趋势总表 和 原始总表)
        df_trend, df_raw_all = smart_save(df_today)
        
        # 4. 生成博客 (用到 趋势总表 和 今天的详细数据)
        # 注意：这里传给 generate_blog 的第二个参数应该是“今天的详细数据”，而不是所有历史
        df_raw_today = df_raw_all[df_raw_all['date'] == TODAY]
        generate_blog(df_trend, df_raw_today)
    else:
        print("今天没爬到数据，跳过更新。")