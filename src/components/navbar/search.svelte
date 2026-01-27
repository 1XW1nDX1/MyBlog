<script lang="ts">
import { onMount, onDestroy } from "svelte";
import Icon from "@iconify/svelte";
import { url } from "@utils/url";
import { navigateToPage } from "@utils/navigation";
import type { SearchResult } from "@/global";
import { i18n } from "@i18n/translation";
import I18nKey from "@i18n/i18nKey";
import DropdownPanel from "@/components/common/DropdownPanel.svelte";

// --- 状态定义 ---
let keywordDesktop = $state("");
let keywordMobile = $state("");
let result: SearchResult[] = $state([]);
let isSearching = $state(false);
let pagefindLoaded = false;
let initialized = $state(false);
let debounceTimer: NodeJS.Timeout;

// 新增：搜索引擎模式 ('site' | 'google' | 'baidu')
type SearchEngine = 'site' | 'google' | 'baidu';
let searchEngine = $state<SearchEngine>('site');

const fakeResult: SearchResult[] = [
    {
        url: url("/"),
        meta: { title: "Dev Mode: Fake Result" },
        excerpt: "Search only works in <mark>production</mark> build.",
    },
    {
        url: url("/"),
        meta: { title: "Switch Engine Test" },
        excerpt: "Try clicking the icon to switch to Google.",
    },
];

// --- 核心逻辑 ---

const togglePanel = () => {
    const panel = document.getElementById("search-panel");
    panel?.classList.toggle("float-panel-closed");
};

// 切换搜索引擎
const toggleEngine = (e: Event) => {
    // 阻止事件冒泡，虽然常驻模式下不那么重要，但好习惯要养成
    e.stopPropagation(); 
    
    // 循环切换逻辑
    if (searchEngine === 'site') searchEngine = 'google';
    else if (searchEngine === 'google') searchEngine = 'baidu';
    else searchEngine = 'site';
    
    // 切换后：清空旧结果，并让输入框获得焦点
    result = [];
    document.getElementById("search-input-desktop")?.focus();
};

const handleBlur = () => {
    // 失去焦点时，延迟隐藏下拉面板（给用户点击结果的时间）
    setTimeout(() => {
        setPanelVisibility(false, true);
    }, 200);
};

// 处理键盘事件：Enter 跳转
const handleKeydown = (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
        const keyword = keywordDesktop || keywordMobile;
        if (!keyword) return;

        // 如果不是站内搜，就跳转
        if (searchEngine !== 'site') {
            e.preventDefault();
            let targetUrl = "";
            if (searchEngine === 'google') {
                targetUrl = `https://www.google.com/search?q=${encodeURIComponent(keyword)}`;
            } else if (searchEngine === 'baidu') {
                targetUrl = `https://www.baidu.com/s?wd=${encodeURIComponent(keyword)}`;
            }
            window.open(targetUrl, '_blank');
            closeSearchPanel(); 
        }
        // 站内搜通常不需要拦截 Enter，除非你想让它跳到第一个结果
    }
};

const setPanelVisibility = (show: boolean, isDesktop: boolean): void => {
    const panel = document.getElementById("search-panel");
    if (!panel || !isDesktop) return;
    show ? panel.classList.remove("float-panel-closed") : panel.classList.add("float-panel-closed");
};

const closeSearchPanel = (): void => {
    const panel = document.getElementById("search-panel");
    panel?.classList.add("float-panel-closed");
    keywordDesktop = "";
    keywordMobile = "";
    result = [];
};

const handleResultClick = (event: Event, url: string): void => {
    event.preventDefault();
    closeSearchPanel();
    navigateToPage(url);
};

const search = async (keyword: string, isDesktop: boolean): Promise<void> => {
    // 安全检查：如果不是站内模式，或者没初始化，就不搜
    if (!keyword || searchEngine !== 'site') {
        setPanelVisibility(false, isDesktop);
        result = [];
        return;
    }
    if (!initialized) return;
    
    isSearching = true;
    try {
        let searchResults: SearchResult[] = [];
        if (import.meta.env.PROD && pagefindLoaded && window.pagefind) {
            const response = await window.pagefind.search(keyword);
            searchResults = await Promise.all(response.results.map((item: any) => item.data()));
        } else if (import.meta.env.DEV) {
            searchResults = fakeResult;
        }
        result = searchResults;
        setPanelVisibility(result.length > 0, isDesktop);
    } catch (error) {
        console.error("Search error:", error);
        result = [];
        setPanelVisibility(false, isDesktop);
    } finally {
        isSearching = false;
    }
};

onMount(() => {
    const initializeSearch = () => {
        initialized = true;
        pagefindLoaded = typeof window !== "undefined" && !!window.pagefind;
    };
    if (import.meta.env.DEV) {
        initializeSearch();
    } else {
        document.addEventListener("pagefindready", initializeSearch);
        setTimeout(() => { if (!initialized) initializeSearch(); }, 2000);
    }
});

// --- 副作用监控 ($effect) ---
$effect(() => {
    if (initialized) {
        const keyword = keywordDesktop || keywordMobile;
        const isDesktop = true; // 现在总是常驻的，所以直接视为 true
        
        clearTimeout(debounceTimer);
        
        // 只有在 site 模式下才自动触发搜索
        if (keyword && searchEngine === 'site') {
            debounceTimer = setTimeout(() => {
                search(keyword, isDesktop);
            }, 300);
        } else {
            // 切到外部引擎时，清空结果面板
            result = [];
            setPanelVisibility(false, isDesktop);
        }
    }
});

onDestroy(() => clearTimeout(debounceTimer));
</script>

<div
    id="search-bar"
    class="hidden lg:flex items-center h-11 rounded-lg w-64 transition-colors relative
           bg-black/[0.04] hover:bg-black/[0.06] focus-within:bg-black/[0.06] 
           dark:bg-white/5 dark:hover:bg-white/10 dark:focus-within:bg-white/10"
>
    <button 
        class="h-full px-3 flex items-center justify-center cursor-pointer transition-transform active:scale-90 hover:text-[var(--primary)] z-10"
        onclick={toggleEngine}
        title="切换搜索引擎: 站内 / Google / Baidu"
        aria-label="Switch Search Engine"
    >
        {#if searchEngine === 'site'}
            <Icon icon="material-symbols:search" class="text-[1.25rem] text-black/50 dark:text-white/50" />
        {:else if searchEngine === 'google'}
            <Icon icon="logos:google-icon" class="text-[1.1rem]" />
        {:else}
            <Icon icon="simple-icons:baidu" class="text-[1.1rem] text-blue-600" />
        {/if}
    </button>

    <input 
        id="search-input-desktop" 
        bind:value={keywordDesktop}
        onfocus={() => {
            if(searchEngine === 'site' && keywordDesktop) search(keywordDesktop, true);
        }}
        onblur={handleBlur}
        onkeydown={handleKeydown} 
        placeholder={
            searchEngine === 'site' ? i18n(I18nKey.search) : 
            searchEngine === 'google' ? "Google Search" : "百度一下"
        }
        class="flex-1 bg-transparent outline-0 text-sm h-full w-full pr-3
               text-black/75 dark:text-white/75 
               placeholder:text-black/30 dark:placeholder:text-white/30"
    >
</div>

<button onclick={togglePanel} aria-label="Search Panel" id="search-switch"
        class="btn-plain scale-animation lg:!hidden rounded-lg w-11 h-11 active:scale-90">
    <Icon icon="material-symbols:search" class="text-[1.25rem]"></Icon>
</button>

<DropdownPanel
        id="search-panel"
        class="float-panel-closed absolute md:w-[30rem] top-20 left-4 md:left-[unset] right-4 z-50 search-panel"
>
    <div id="search-bar-inside" class="flex relative lg:hidden transition-all items-center h-11 rounded-xl
      bg-black/[0.04] hover:bg-black/[0.06] focus-within:bg-black/[0.06]
      dark:bg-white/5 dark:hover:bg-white/10 dark:focus-within:bg-white/10
    ">
        <Icon icon="material-symbols:search" class="absolute text-[1.25rem] pointer-events-none ml-3 transition my-auto text-black/30 dark:text-white/30"></Icon>
        <input placeholder="Search" bind:value={keywordMobile}
               class="pl-10 absolute inset-0 text-sm bg-transparent outline-0
               focus:w-60 text-black/50 dark:text-white/50"
        >
    </div>

    {#each result as item}
        <a href={item.url}
           onclick={(e) => handleResultClick(e, item.url)}
           class="transition first-of-type:mt-2 lg:first-of-type:mt-0 group block
       rounded-xl text-lg px-3 py-2 hover:bg-[var(--btn-plain-bg-hover)] active:bg-[var(--btn-plain-bg-active)]">
            <div class="transition text-90 inline-flex font-bold group-hover:text-[var(--primary)]">
                {item.meta.title}<Icon icon="fa6-solid:chevron-right" class="transition text-[0.75rem] translate-x-1 my-auto text-[var(--primary)]"></Icon>
            </div>
            <div class="transition text-sm text-50">
                {@html item.excerpt}
            </div>
        </a>
    {/each}
</DropdownPanel>

<style>
    input:focus { outline: 0; }
    :global(.search-panel) { max-height: calc(100vh - 100px); overflow-y: auto; }
</style>