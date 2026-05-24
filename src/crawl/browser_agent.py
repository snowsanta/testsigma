import json
from typing import List, Optional
from playwright.sync_api import sync_playwright, Page, Browser
from src.crawl.artifacts import CrawlArtifactBundle, DOMSnapshot, Transition
import src.llm.client

class PlaywrightExecutor:
    """Real Playwright browser executor using headless Chromium."""

    def __init__(self):
        self.playwright = None
        self.browser: Optional[Browser] = None
        self.page: Optional[Page] = None

    def start(self):
        self.playwright = sync_playwright().start()
        self.browser = self.playwright.chromium.launch(headless=True)
        self.page = self.browser.new_page()

    def navigate(self, url: str) -> str:
        self.page.goto(url, wait_until="networkidle", timeout=30000)
        return self.page.content()

    def click(self, selector: str):
        self.page.click(selector, timeout=10000)
        self.page.wait_for_load_state("networkidle", timeout=30000)

    def type_text(self, selector: str, value: str):
        self.page.fill(selector, value, timeout=10000)

    def current_url(self) -> str:
        return self.page.url

    def current_html(self) -> str:
        return self.page.content()

    def close(self):
        if self.page:
            self.page.close()
        if self.browser:
            self.browser.close()
        if self.playwright:
            self.playwright.stop()


class LLMPlanner:
    """Uses LLM to decide the next browser navigation action from DOM state."""

    SYSTEM_PROMPT = (
        "You are a browser automation agent. Given a list of interactive elements "
        "on the current page, decide what action to take next to explore the application. "
        "Respond with valid JSON only. No other text."
    )

    def next_action(self, url: str, elements: List[dict], max_steps: int) -> dict:
        elements_json = json.dumps(elements, indent=2)

        user_prompt = (
            f"Current URL: {url}\n\n"
            f"Interactive elements on this page:\n{elements_json}\n\n"
            f"Choose ONE action:\n"
            f'  - click a button or link: {{"action": "click", "selector": "css-selector", "reason": "..."}}\n'
            f'  - type into an input: {{"action": "type", "selector": "css-selector", "value": "text to type", "reason": "..."}}\n'
            f'  - stop exploring: {{"action": "stop", "reason": "..."}}\n\n'
            f"Prefer navigation elements (links, buttons) over form inputs. "
            f"Stop after exploring key pages. Do not repeat pages already visited."
        )

        response_str = src.llm.client.complete(
            system=self.SYSTEM_PROMPT, user=user_prompt
        )

        try:
            # Extract JSON from response (handle markdown code fences)
            cleaned = response_str.strip()
            if cleaned.startswith("```"):
                cleaned = cleaned.split("\n", 1)[1]
                if cleaned.endswith("```"):
                    cleaned = cleaned[:-3]
            return json.loads(cleaned)
        except (json.JSONDecodeError, KeyError):
            return {"action": "stop", "reason": "LLM returned unparseable action"}


class BrowserAgent:
    """Coordinates Playwright executor and LLM planner for autonomous crawling."""

    def __init__(self, max_steps: int = 10):
        self.max_steps = max_steps
        self.executor = PlaywrightExecutor()
        self.planner = LLMPlanner()

    def run(self, start_url: str) -> CrawlArtifactBundle:
        snapshots: List[DOMSnapshot] = []
        transitions: List[Transition] = []
        visited_urls: set = set()

        self.executor.start()

        try:
            html = self.executor.navigate(start_url)
            current_url = self.executor.current_url()
            visited_urls.add(current_url)

            snapshot = DOMSnapshot.from_html(html, url=current_url)
            snapshots.append(snapshot)

            for step in range(self.max_steps):
                action = self.planner.next_action(
                    url=current_url,
                    elements=snapshot.elements,
                    max_steps=self.max_steps,
                )

                if action.get("action") == "stop":
                    break

                action_type = action.get("action", "stop")
                selector = action.get("selector", "")
                reason = action.get("reason", "")

                try:
                    if action_type == "click":
                        self.executor.click(selector)
                    elif action_type == "type":
                        value = action.get("value", "")
                        self.executor.type_text(selector, value)
                    else:
                        break
                except Exception as e:
                    transitions.append(
                        Transition(
                            from_url=current_url,
                            to_url=current_url,
                            action=f"{action_type}_failed",
                            element_selector=selector,
                        )
                    )
                    if not snapshots:
                        snapshots.append(
                            DOMSnapshot.from_html(
                                self.executor.current_html(),
                                url=current_url,
                            )
                        )
                    continue

                new_url = self.executor.current_url()
                new_html = self.executor.current_html()
                transition = Transition(
                    from_url=current_url,
                    to_url=new_url,
                    action=action_type,
                    element_selector=selector,
                )
                transitions.append(transition)

                current_url = new_url

                # Only add snapshot if we haven't seen this URL
                if current_url not in visited_urls:
                    visited_urls.add(current_url)
                    snapshot = DOMSnapshot.from_html(new_html, url=current_url)
                    snapshots.append(snapshot)

        finally:
            self.executor.close()

        return CrawlArtifactBundle(snapshots=snapshots, transitions=transitions)
