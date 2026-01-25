import json
import csv
import re
import os
import datetime
import time
import random
import pandas as pd
from DrissionPage import ChromiumPage, ChromiumOptions
# [新增] 引入虚拟显示器库
from pyvirtualdisplay import Display

# ================= 🔧 路径智能配置区域 =================
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
BLOG_POST_PATH = os.path.join(PROJECT_ROOT, 'src', 'content', 'posts', 'memory-monitor.mdx')
DATA_DIR = os.path.join(CURRENT_DIR, 'data_storage')
RAW_FILE = os.path.join(DATA_DIR, 'jd_memory_raw.csv')
TREND_FILE = os.path.join(DATA_DIR, 'jd_memory_trend.csv')

os.makedirs(DATA_DIR, exist_ok=True)
TODAY = datetime.date.today().strftime('%Y-%m-%d')

print(f"📂 路径检查:\n- 脚本位置: {CURRENT_DIR}\n- 博客输出: {BLOG_POST_PATH}\n- 数据存储: {DATA_DIR}")

# ================= 🕷️ 爬虫部分 (Xvfb + 多页翻页版) =================
def crawl_jd_data():
    print(f"[{TODAY}] 哀酱正在启动虚拟显示环境 (Xvfb)...")
    
    # [新增] 启动虚拟显示器 (模拟 1080P 屏幕)
    # visible=False 表示不显示真实窗口（在服务器后台运行）
    # size=(1920, 1080) 强制渲染大窗口，确保所有元素都能被 locate 到
    with Display(visible=False, size=(1920, 1080)) as disp:
        
        print("🖥️ 虚拟显示器已就绪，正在启动 Edge 浏览器...")
        co = ChromiumOptions()
        
        # [GitHub Actions 适配]
        if os.path.exists('/usr/bin/microsoft-edge-stable'):
            co.set_browser_path('/usr/bin/microsoft-edge-stable')
            
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-gpu')
        
        # [修改] 关键点：这里必须设为 False！
        # 因为我们已经有了 Xvfb 提供的虚拟屏幕，不需要浏览器自带的无头模式了
        # 这样 DrissionPage 就能通过坐标精准点击元素
        
        co.set_argument('--window-size=1920,1080')
        
        
        # 实例化浏览器
        cookies = 'pt_key=AAJpdcJ-ADAQLmg0N4rJ_YguZ75M9bKgUIGPLOWTgor819BJY9aQpZtLEi34B2SNOKL6zqOcOBU; pt_pin=jd_CtWcPYgxylRA; domain=jd.com'
        edge = ChromiumPage(co)
        edge.set.cookies(cookies)
        captured_data = []

        try:
            # 1. 启动监听 (只用启动一次)
            edge.listen.start("?appid=search-pc-java&t=")
            
            # 2. 访问首页
            print("正在访问京东搜索页...")
            edge.get("https://search.jd.com/Search?keyword=%E5%86%85%E5%AD%98%E6%9D%A1&enc=utf-8&wq=neicunt")
            
            # --- 循环抓取 10 页 ---
            target_pages = 10
            for page in range(1, target_pages + 1):
                print(f"\n--- 正在处理第 {page}/{target_pages} 页 ---")
                
                # [动作 1] 滚动到底部触发懒加载
                print("正在缓慢滚动页面...")
                # 因为有虚拟界面，scroll.to_see 现在会非常精准
                next_p = edge.ele('text=下一页')
                edge.scroll.to_see(next_p)
                
                # [动作 2] 等待数据包
                print("等待数据包加载...")
                resp_list = edge.listen.wait(count=5, timeout=60)
                
                if isinstance(resp_list, bool):
                    print(f"⚠️ 第 {page} 页等待超时，可能数据加载不全。")
                    resp_list = []

                # [动作 3] 解析当前页数据
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

                    if isinstance(json_data, dict) and "data" in json_data and isinstance(json_data["data"], dict) and "wareList" in json_data["data"]:
                        for item in json_data["data"]["wareList"]:
                            title = item.get('wareName', '')
                            price = item.get('realPrice', '0')
                            link = f"https://item.jd.com/{item.get('wareId')}.html"
                            clean_title = re.sub('<.*?>', '', title)
                            
                            captured_data.append({
                                'date': TODAY, 'title': clean_title, 'price': price, 'link': link
                            })
                            page_count += 1
                
                print(f"✅ 第 {page} 页抓取完成，本页捕获约 {page_count} 条数据。")

                # [动作 4] 如果不是最后一页，点击“下一页”
                if page < target_pages:
                    next_btn = edge.ele('text=下一页')
                    
                    if next_btn:
                        print("找到下一页按钮，准备点击...")
                        # 这里的点击现在是在虚拟屏幕上进行的真实点击
                        next_btn.click() 
                        
                        sleep_time = random.uniform(2, 5)
                        print(f"😴 哀酱累了，休息 {sleep_time:.2f} 秒再继续...")
                        time.sleep(sleep_time)
                    else:
                        print("❌ 未找到下一页按钮，可能已经到底或被反爬，提前结束。")
                        break
                
        except Exception as e:
            print(f"❌ 严重错误: {e}")
            print(f"❌ 严重错误: {e}")
            
            # [关键新增] 报错时的现场取证！
            print(f"🔍 [调试信息] 当前 URL: {edge.url}")
            print(f"🔍 [调试信息] 当前 标题: {edge.title}")
            
            # 截图保存到 data_storage 文件夹，稍后通过 Actions 上传
            screenshot_path = os.path.join(DATA_DIR, 'error_screenshot.png')
            edge.get_screenshot(path=screenshot_path)
            print(f"📸 错误截图已保存: {screenshot_path}")
            
            # 保存 HTML 源码，方便分析结构
            html_path = os.path.join(DATA_DIR, 'error_page.html')
            with open(html_path, 'w', encoding='utf-8') as f:
                f.write(edge.html)
            print(f"📄 错误页面源码已保存: {html_path}")
            
            # 重新抛出异常，让 Action 显示红色失败状态
            raise e
        finally:
            edge.quit()
            print("浏览器已关闭，虚拟显示器即将释放。")

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
    
    mdx_content += "\n\n*Generated by Haibara Ai (Ver. MultiPage)*"

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