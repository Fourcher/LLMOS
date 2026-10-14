# 01 browser

## Task and verdict

**Task:** Use the web browser like a normal person: open it, go to wikipedia.org, search "Alpine Linux", open the article, scroll down, go back, open example.com, close the browser. Note whether pages load, how long each step takes, whether typing an address works, and whether the window can be moved, resized and closed.

**Verdict: WORKS (with friction).** Every step of the task completed on the VM (LLM OS 1.8.5, Firefox). I could not reproduce "the browser doesn't work" on this VM. Move and resize by dragging could not be tested (see Steps and Friction).

## Steps

Times are from the vmuser timestamps (wall clock, 11:13 to 11:15, 14 Oct).

1. **Start screen.** `shot 01-start`. Desk shows a "While you were away" window (LLM OS 1.8.5 installed), a greeting bubble, and the request box. Top bar has a grid icon at (807,23), no visible browser icon.
2. **Ask for the browser: `say "open the browser"`.** Reply "Opened Firefox in a window." after 3 s. Firefox was on screen with duckduckgo.com (still loading) by 11:13:46, about 5 s after the request. Shot `01-open-browser-say`. Expected a browser opening on a blank or search page; it opened on DuckDuckGo, which is the default home page. Fine, but a person would not know that is the home page.
3. **Type an address: click the address bar (600,64), type `wikipedia.org`, Enter.** Typing and Enter worked. Page showed as www.wikipedia.org at 11:13:56, about 7 s after pressing Enter. Shot `01-wikipedia-typed`. A donation panel ("The internet's changing", "Donate now") covered the search box.
4. **Dismiss the donation panel.** Clicked the small chevron (1234,185), which folded it to a bottom bar. Closed the bar with its X (1245,645). Shot `01-wiki-banner-min`, `01-banner-closed` (later).
5. **Search "Alpine Linux".** Clicked the search box (580,580), typed `Alpine Linux`, Enter at 11:14:05. Article "Alpine Linux - Wikipedia" was on screen at 11:14:10, about 5 s. Shot `01-wiki-search`. The URL became en.wikipedia.org/wiki/Alpine_Linux.
6. **Open the article and handle a second donation panel.** A second panel ("Please select an amount", "Maybe later") covered the top. I clicked "Maybe later" (1082,584). That opened a new dialog, "How would you like to be reminded?", asking for an email or text message. I went back (arrow at 366,316) and closed the panel with its X (1229,183). Article body readable at 11:14:20. Shot `01-article-top` (dialog), `01-banner-closed`.
7. **Scroll down.** Problem on my side: I clicked the article body at (640,500) to focus it, and that hit the "stack-smashing protection" link. The page went to "Buffer overflow protection" (11:14:24). Then `key space` failed (see Bugs, the tool, not the browser). I used `key pgdn` twice (11:14:28 to 11:14:30). Scrolling worked, and the Contents sidebar and Appearance panel stayed fixed. Shot `01-scrolled-a`.
8. **Go back.** Clicked the Back arrow (24,64) at 11:14:35. Alpine Linux article back on screen by 11:14:37, about 2 s, scroll position reset to top. A hover preview popup for "Buffer overflow protection" appeared because the mouse was over a link. Shot `01-after-back`.
9. **Open example.com.** Clicked the address bar (600,64), typed `example.com`, Enter at 11:14:41. Loaded by 11:14:45, about 4 s. Page "Example Domain" shown with its notice text in several languages. Shot `01-example`.
10. **Window move and resize.** Window has no visible title bar; the browser fills the 1280x800 screen. The compositor is labwc (Wayland). Double-clicking the empty tab strip (700,36) un-maximized the window. It became a window about 1204x772 at (38,14), with a visible border. A second double-click on it (700,36) maximized it again. Shot `01-dblclick-tabbar2`, `01-restored-max`. **Dragging to move, and dragging an edge to resize, could not be tested.** vmuser.py has no drag command.
11. **Close the browser.** Clicked the window X at the top right (1257,22) at 11:15:11. Browser gone in about 2 s. The desk came back with the "While you were away" window. In the VM, `ps` found 0 Firefox processes afterwards. Shot `01-after-close`. No save or "close tabs?" prompt appeared.

Extra, to answer "look for a way to open it by clicking":

12. **Grid icon at the top bar (807,23).** Opened an "Apps" window with a PROGRAMS list that includes **Firefox** (1120,220). A bubble "Here they are." appeared. Clicking Firefox opened it at about 4 s (11:15:21 to 11:15:25), on DuckDuckGo with a bar "Open previous tabs?" and a "Optional AI" tip. Shot `01-launcher`, `01-firefox-from-tile`. Closed Firefox (1257,22); closed the Apps window (1233,89). Final state: desk, no Firefox running. Shot `01-final`.

## Bugs

No hard failures in the browser. Problems found:

1. **Donation dialog on Wikipedia asks for contact details.** Clicking "Maybe later" on the Wikipedia banner (1082,584) opened "How would you like to be reminded?" with "Send me an email" and "Send me a text message". This is Wikipedia's page, not LLM OS, but a normal person would likely think they had to give an email. Expected: "Maybe later" just closes the banner. Note for the owner: the banner stays on every visit, and the close X works only after the dialog is backed out of.
2. **Tool, not browser: `vmuser.py key space` fails.** Error from qmp.py: `Parameter 'data' does not accept value 'space'`. Test-tool only, but it stops "scroll with the space bar". Workaround: `key pgdn`.
3. **No way to scroll with a wheel or drag in vmuser.py.** Only click, double, right, type and key. Scrolling by mouse wheel and dragging the window could not be tested. This is a limit of my test tool, not a product bug, but the owner's complaint could be about exactly these.

## Friction

- **Opening the browser by text goes to a site, not a blank page.** "open the browser" showed duckduckgo.com. Users may expect a start page or an address bar with focus.
- **Address bar is not focused on open.** I had to click it at (600,64) before typing. Typing `wikipedia.org` then Enter worked straight away.
- **Start-up prompts in Firefox.** "Open previous tabs?" bar and an "Optional AI" tooltip on DuckDuckGo, both on first use from the Apps tile. Both need closing before the page is usable.
- **Two donation banners on Wikipedia**, one at the bottom, one as a side panel. The first is folded by a chevron; the second has "Maybe later". Together they cover the search box and the top of the article. Took about 4 extra clicks.
- **Hover popups.** Moving the mouse over a link shows a preview card (for example "Buffer overflow protection"). It can cover text while reading.
- **Window has no title bar.** Users can only close with the small X in the tab strip, un-maximize with a double-click on the empty tab strip, and only a person who knows that trick would find it. No visible minimize or maximize buttons.
- **Waiting.** Every page took 4 to 7 s to show. Nothing too slow, but there is no visible progress for "say" until the page starts to show.

## Ideas

- Start the browser on a blank tab or the search box, with the address bar focused.
- Show minimize, maximize and close buttons on the browser window (or a title bar) so users can find them.
- Turn off the donation and "Optional AI" prompts for the bundled Firefox profile, or make "Maybe later" close the banner.
- Add a `vmuser.py scroll` and `drag` command so the next tester can check wheel scrolling and window move/resize.
- Make `vmuser.py key space` work so "press space to scroll" can be tested.

## Timings (summary)

| Step | Time |
|---|---|
| "open the browser" reply | 3 s (page visible ~5 s) |
| Type wikipedia.org + Enter to page | ~7 s |
| Wikipedia search "Alpine Linux" to article | ~5 s |
| Back button | ~2 s |
| Type example.com + Enter to page | ~4 s |
| Grid icon, Apps tile, Firefox window | ~4 s |
| Close window (X) | ~2 s |

## Screenshots

All under `run/sweep/shots/` in the Support files folder: `01-start`, `01-open-browser-say`, `01-wikipedia-typed`, `01-wiki-banner-min`, `01-wiki-search`, `01-article-top`, `01-banner-closed`, `01-scrolled-a`, `01-after-back`, `01-example`, `01-dblclick-tabbar`, `01-dblclick-tabbar2`, `01-restored-max`, `01-after-close`, `01-launcher`, `01-firefox-from-tile`, `01-closed-2nd`, `01-final`.
