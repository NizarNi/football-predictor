
import asyncio
import json
import os
from datetime import datetime
import sys
import time

# Check if puppeteer-python is installed, if not install it
try:
    from pyppeteer import launch
except ImportError:
    print("Installing required packages...")
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyppeteer"])
    from pyppeteer import launch

BASE_URL = "https://www.flashscore.com"
OUTPUT_DIR = "scraped_data"

# Ensure output directory exists
os.makedirs(OUTPUT_DIR, exist_ok=True)

async def open_page_and_navigate(browser, url):
    page = await browser.newPage()
    await page.setViewport({"width": 1366, "height": 768})
    await page.setUserAgent("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    await page.goto(url, {"waitUntil": "networkidle0", "timeout": 60000})
    return page

async def wait_for_selector(page, selector, timeout=10000):
    try:
        await page.waitForSelector(selector, {"timeout": timeout})
        return True
    except Exception as e:
        print(f"Warning: Could not find selector \'{selector}\': {e}")
        return False

async def extract_match_data(page):
    return await page.evaluate("""() => {
        return {
            stage: document.querySelector(".tournamentHeader__country > a")?.innerText.trim(),
            date: document.querySelector(".duelParticipant__startTime")?.innerText.trim(),
            status: document.querySelector(".fixedHeaderDuel__detailStatus")?.innerText.trim(),
            home: {
                name: document.querySelector(".duelParticipant__home .participant__participantName.participant__overflow")?.innerText.trim(),
                image: document.querySelector(".duelParticipant__home .participant__image")?.src,
            },
            away: {
                name: document.querySelector(".duelParticipant__away .participant__participantName.participant__overflow")?.innerText.trim(),
                image: document.querySelector(".duelParticipant__away .participant__image")?.src,
            },
            result: {
                home: Array.from(document.querySelectorAll(".detailScore__wrapper span:not(.detailScore__divider)"))?.[0]?.innerText.trim(),
                away: Array.from(document.querySelectorAll(".detailScore__wrapper span:not(.detailScore__divider)"))?.[1]?.innerText.trim(),
                regulationTime: document
                    .querySelector(".detailScore__fullTime")
                    ?.innerText.trim()
                    .replace(/[\\n()]/g, ""),
                penalties: Array.from(document.querySelectorAll("[data-testid=\"wcl-scores-overline-02\"]"))
                    .find((element) => element.innerText.trim().toLowerCase() === "penalties")
                    ?.nextElementSibling?.innerText?.trim()
                    .replace(/\\s+/g, ""),
            },
        };
    }""")

async def extract_match_information(page):
    return await page.evaluate("""() => {
        const elements = Array.from(document.querySelectorAll("div[data-testid='wcl-summaryMatchInformation'] > div"));
        return elements.reduce((acc, element, index) => {
            if (index % 2 === 0) {
                acc.push({
                    category: element?.textContent
                        .trim()
                        .replace(/\\s+/g, " ")
                        .replace(/(^[:\\s]+|[:\\s]+$|:)/g, ""),
                    value: elements[index + 1]?.innerText
                        .trim()
                        .replace(/\\s+/g, " ")
                        .replace(/(^[:\\s]+|[:\\s]+$|:)/g, ""),
                });
            }
            return acc;
        }, []);
    }""")

async def extract_match_statistics(page):
    return await page.evaluate("""() => {
        return Array.from(document.querySelectorAll("div[data-testid='wcl-statistics']")).map((element) => ({
            category: element.querySelector("div[data-testid='wcl-statistics-category']")?.innerText.trim(),
            homeValue: Array.from(element.querySelectorAll("div[data-testid='wcl-statistics-value'] > strong"))?.[0]?.innerText.trim(),
            awayValue: Array.from(element.querySelectorAll("div[data-testid='wcl-statistics-value'] > strong"))?.[1]?.innerText.trim(),
        }));
    }""")

async def extract_betting_analysis(page):
    """Extract betting analysis from the summary section"""
    try:
        # Check if betting analysis section exists
        has_betting = await page.evaluate("""() => {
            const sections = Array.from(document.querySelectorAll('.matchSummaryRow__title'));
            return sections.some(section => section.innerText.includes('Betting Analysis') || 
                                           section.innerText.includes('Betting') || 
                                           section.innerText.includes('Analysis'));
        }""")
        
        if not has_betting:
            print("No betting analysis section found")
            return {}
            
        # Extract betting analysis data
        return await page.evaluate("""() => {
            const bettingData = {};
            
            // Find the betting analysis section
            const sections = Array.from(document.querySelectorAll('.matchSummaryRow__title'));
            const bettingSection = sections.find(section => 
                section.innerText.includes('Betting Analysis') || 
                section.innerText.includes('Betting') || 
                section.innerText.includes('Analysis')
            );
            
            if (!bettingSection) return bettingData;
            
            // Get the parent container of the betting section
            const container = bettingSection.closest('.matchSummaryRow');
            if (!container) return bettingData;
            
            // Extract all betting insights
            const insights = Array.from(container.querySelectorAll('.matchSummaryRow__item'));
            
            insights.forEach(insight => {
                const title = insight.querySelector('.matchSummaryRow__itemTitle')?.innerText.trim();
                const content = insight.querySelector('.matchSummaryRow__itemContent')?.innerText.trim();
                
                if (title && content) {
                    bettingData[title] = content;
                }
            });
            
            return bettingData;
        }""")
    except Exception as e:
        print(f"Error extracting betting analysis: {e}")
        return {}

async def extract_odds_data(page):
    """Extract odds data if available"""
    try:
        # Navigate to the odds tab
        odds_url = page.url.split('#')[0] + '#/odds-comparison/1x2-odds/full-time'
        await page.goto(odds_url, {"waitUntil": "networkidle0"})
        
        # Wait for odds data to load
        await wait_for_selector(page, ".ui-table__body", 20000)
        
        # Extract odds data
        return await page.evaluate("""() => {
            const oddsData = {
                home: [],
                draw: [],
                away: []
            };
            
            // Get all bookmakers and their odds
            const rows = Array.from(document.querySelectorAll('.ui-table__row'));
            
            rows.forEach(row => {
                const bookmaker = row.querySelector('.oddsCell__bookmakerPart')?.innerText.trim();
                if (!bookmaker) return;
                
                const odds = Array.from(row.querySelectorAll('.oddsCell__odd'));
                
                if (odds.length >= 3) {
                    oddsData.home.push({
                        bookmaker,
                        odds: odds[0]?.innerText.trim()
                    });
                    
                    oddsData.draw.push({
                        bookmaker,
                        odds: odds[1]?.innerText.trim()
                    });
                    
                    oddsData.away.push({
                        bookmaker,
                        odds: odds[2]?.innerText.trim()
                    });
                }
            });
            
            return oddsData;
        }""")
    except Exception as e:
        print(f"Error extracting odds data: {e}")
        return {}

async def get_match_data_async(browser, match_id):
    """Get comprehensive data for a specific match"""
    print(f"Fetching data for match ID: {match_id}")
    
    # Navigate to match summary page
    page = await open_page_and_navigate(browser, f"{BASE_URL}/match/{match_id}/#/match-summary")
    
    # Wait for key elements to load
    await wait_for_selector(page, ".duelParticipant__startTime")
    await wait_for_selector(page, "div[data-testid='wcl-summaryMatchInformation'] > div")
    
    # Extract basic match data
    match_data = await extract_match_data(page)
    information = await extract_match_information(page)
    
    # Extract betting analysis from summary section
    betting_analysis = await extract_betting_analysis(page)
    
    # Navigate to statistics tab
    stats_url = page.url.split('#')[0] + '#/match-summary/match-statistics/0'
    await page.goto(stats_url, {"waitUntil": "networkidle0"})
    await wait_for_selector(page, "div[data-testid='wcl-statistics']")
    
    # Extract match statistics
    statistics = await extract_match_statistics(page)
    
    # Extract odds data
    odds_data = await extract_odds_data(page)
    
    # Close the page
    await page.close()
    
    # Combine all data
    return {
        **match_data,
        "information": information,
        "statistics": statistics,
        "betting_analysis": betting_analysis,
        "odds": odds_data
    }

async def search_matches_async(browser, search_term):
    """Search for matches by team name"""
    print(f"Searching for matches with: {search_term}")
    
    # Navigate to Flashscore homepage
    page = await open_page_and_navigate(browser, BASE_URL)
    
    # Click on search icon
    await wait_for_selector(page, ".searchIcon")
    await page.click(".searchIcon")
    
    # Wait for search input and enter search term
    await wait_for_selector(page, ".searchInput__input")
    await page.type(".searchInput__input", search_term)
    
    # Wait for search results
    await wait_for_selector(page, ".searchResult", 10000)
    
    # Extract match IDs from search results
    match_results = await page.evaluate("""(searchTerm) => {
        const results = [];
        const items = Array.from(document.querySelectorAll('.searchResult'));
        
        items.forEach(item => {
            // Check if it's a match result
            const isMatch = item.querySelector('.searchResult__participantName');
            if (!isMatch) return;
            
            // Get match details
            const homeTeam = item.querySelector('.searchResult__participantName--home')?.innerText.trim();
            const awayTeam = item.querySelector('.searchResult__participantName--away')?.innerText.trim();
            
            // Only include if it matches our search term
            if (homeTeam?.toLowerCase().includes(searchTerm.toLowerCase()) || 
                awayTeam?.toLowerCase().includes(searchTerm.toLowerCase())) {
                
                const matchId = item.getAttribute('href')?.match(/match\\/([^/]+)/)?.[1];
                const date = item.querySelector('.searchResult__date')?.innerText.trim();
                const league = item.querySelector('.searchResult__tournament')?.innerText.trim();
                
                if (matchId) {
                    results.push({
                        id: matchId,
                        homeTeam,
                        awayTeam,
                        date,
                        league
                    });
                }
            }
        });
        
        return results;
    }""", search_term)
    
    # Close the page
    await page.close()
    
    return match_results

async def get_upcoming_matches_async(browser, league_name=None, days_ahead=7):
    """Get upcoming matches, optionally filtered by league"""
    print(f"Fetching upcoming matches for the next {days_ahead} days")
    
    # Navigate to Flashscore homepage or league page
    url = BASE_URL
    if league_name:
        # This is a simplified approach - in reality, you'd need to map league names to URLs
        url = f"{BASE_URL}/football/{league_name.lower().replace(' ', '-')}"
    
    page = await open_page_and_navigate(browser, url)
    
    # Switch to scheduled matches
    try:
        await wait_for_selector(page, ".filters__tab--scheduled", 5000)
        await page.click(".filters__tab--scheduled")
        await page.waitForTimeout(1000)  # Wait for content to update
    except:
        print("Could not find scheduled matches tab, using default view")
    
    # Extract upcoming matches
    upcoming_matches = await page.evaluate("""() => {
        const results = [];
        const items = Array.from(document.querySelectorAll('.event__match'));
        
        items.forEach(item => {
            const matchId = item.id?.replace('g_1_', '');
            if (!matchId) return;
            
            const homeTeam = item.querySelector('.event__participant--home')?.innerText.trim();
            const awayTeam = item.querySelector('.event__participant--away')?.innerText.trim();
            const dateTime = item.querySelector('.event__time')?.innerText.trim();
            const league = item.closest('.sportName')?.querySelector('.event__title--name')?.innerText.trim();
            
            if (matchId && homeTeam && awayTeam) {
                results.push({
                    id: matchId,
                    homeTeam,
                    awayTeam,
                    dateTime,
                    league
                });
            }
        });
        
        return results;
    }""")
    
    # Close the page
    await page.close()
    
    return upcoming_matches

def run_async_function(coro):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()

def search_matches_sync(search_term):
    async def _search_matches_wrapper():
        browser = await launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        try:
            return await search_matches_async(browser, search_term)
        finally:
            await browser.close()
    return run_async_function(_search_matches_wrapper())

def get_match_data_sync(match_id):
    async def _get_match_data_wrapper():
        browser = await launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        try:
            return await get_match_data_async(browser, match_id)
        finally:
            await browser.close()
    return run_async_function(_get_match_data_wrapper())

def get_upcoming_matches_sync(league_name=None, days_ahead=7):
    async def _get_upcoming_matches_wrapper():
        browser = await launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        try:
            return await get_upcoming_matches_async(browser, league_name, days_ahead)
        finally:
            await browser.close()
    return run_async_function(_get_upcoming_matches_wrapper())


async def main():
    # Launch browser
    browser = await launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
    
    try:
        # Example: Search for matches by team name
        search_results = await search_matches_async(browser, "Arsenal")
        print(f"Found {len(search_results)} matches for Arsenal")
        
        if search_results:
            # Get data for the first match
            match_data = await get_match_data_async(browser, search_results[0]['id'])
            
            # Save to file
            output_file = os.path.join(OUTPUT_DIR, f"match_{search_results[0]['id']}.json")
            with open(output_file, 'w') as f:
                json.dump(match_data, f, indent=2)
            
            print(f"Match data saved to {output_file}")
        
        # Example: Get upcoming matches
        upcoming = await get_upcoming_matches_async(browser)
        print(f"Found {len(upcoming)} upcoming matches")
        
        # Save to file
        upcoming_file = os.path.join(OUTPUT_DIR, "upcoming_matches.json")
        with open(upcoming_file, 'w') as f:
            json.dump(upcoming, f, indent=2)
        
        print(f"Upcoming matches saved to {upcoming_file}")
        
    finally:
        await browser.close()

if __name__ == "__main__":
    asyncio.get_event_loop().run_until_complete(main())

