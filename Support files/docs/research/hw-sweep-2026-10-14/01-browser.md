# 01 Browser (tester 01)

## Task
Use the web browser like a normal person on the real laptop: open Wikipedia, go to bbc.com, search the web, open YouTube and play a video, use tabs, close the browser with its X, use "close the browser" and "go back", look for graphics or layout problems. Close everything at the end.

## Verdict
PARTLY. The browser itself works well on this laptop (pages load, scroll, video plays, tabs and X close are fine). The main problem is that the request box is hidden behind an open browser window, so requests typed while a browser is open go nowhere (or into the page), with no sign to the user.

## Steps
1. "open wikipedia.org". Reply "Opened Firefox on https://wikipedia.org." in 3 s. Page showed within a few seconds. Firefox opened as a window at 160-1760 px wide. Screenshot: dev-01-wiki.
2. Clicked the address bar (800,139), ctrl+l, typed "bbc.com", enter. Page loaded within about 5 s, layout correct, scrolled down 3 ticks with the wheel, page moved smoothly. Screenshots: dev-01-bbc, dev-01-bbc-scrolled.
3. "search the web for best pizza dough recipe". First attempt: no reply at all (state still showed the old reply). Second attempt: same. Cause: the request box sits under the Firefox window and was not reachable. Clicking the visible desktop strip (70,600) first, then "say" again, worked: reply "Opened Firefox searching for 'best pizza dough recipe'." in 3 s. Opened a new tab with DuckDuckGo results, readable and correctly drawn. Screenshots: dev-01-search, dev-01-search2 (failed attempt), dev-01-search3 (works).
4. "open youtube". Reply in 3 s. YouTube home showed a loading skeleton for about 6 s (status bar "Waiting for www.google.com..."), then loaded at about 10 s with "Try searching to get started" (empty feed, expected for a new profile). Searched "pizza dough" (click search box, type, enter): results in about 6 s, thumbnails drawn fine. Clicked a video (The New York Times, 9.7M views): the video played, captions ran, the tab showed the speaker icon, picture looked smooth with no visible tearing or black frames. Closed the YouTube tab with its X. Screenshots: dev-01-youtube, dev-01-youtube2, dev-01-yt-results, dev-01-yt-play2, dev-01-yt-closed.
5. ctrl+t, ctrl+l, typed "wikipedia.org", enter: loaded in about 6 s. Clicked the BBC tab to switch (works), then closed the pizza-search tab with its X (works). Screenshots: dev-01-newtab-wiki, dev-01-switched, dev-01-tab-closed.
6. Closed the browser with the window X (1732,88): closed at once, desk clean, state shows no apps. Screenshot: dev-01-x-closed.
   Then "open wikipedia.org" (reply 3 s), desk click, "close the browser": reply "Closed the browser." in 3 s, no windows left. Screenshot: dev-01-close-cmd.
   Then "open wikipedia.org" (reply 2 s), clicked English on the page (the next page did load), desk click, "go back": reply "Back." in 2 s, page returned to the Wikipedia start page and Forward became enabled. Screenshot: dev-01-goback.
7. Final check: browser closed with its X, state shows no apps, no Firefox process left. Screenshot: dev-01-final.

Graphics: no black frames, glitches, or colour problems seen on any page or video. Layout at 1920x1200 fine. Taskbar text in the bottom bar was partly covered by the browser window (see Bugs).

## Bugs
1. **Request box hidden while a browser is open (main problem).** With the Firefox window open, the request box at the bottom of the screen is behind the window (window spans x 160-1760, the box spans x 295-1625). Typing with "say" then does nothing visible: the reply does not change, and the text lands in the page (or nowhere). Expected: the request box stays usable, or the window leaves room for it, or a person can see it is busy. Workaround that worked: click the desk strip at x 70 first. Happened on step 3 (twice), reproduced: first "search the web..." after the BBC page was open.
   The same is true of any request while a browser window is on screen, so a normal person would think the computer ignored them.
2. **Browser window covers the bottom app bar.** The Firefox window bottom edge (about y 1140) covers the lower dock (Settings, Files, Lists, the Firefox chip). The Firefox chip with its X is partly visible under the window. Expected: the window stops above the bar, or the bar stays on top.
3. **Stale reply in state.** While a browser was open, `state` showed "windows": [] with "apps": ["Firefox"], and it showed the previous reply until the next request. Minor, but it makes it hard to tell whether a request was received.
4. **Tab hover preview stays on screen.** After closing a tab with its X, the hover card for the Wikipedia tab stayed over the page for a moment (dev-01-tab-closed). Minor.

## Friction and Ideas
- YouTube's home page is empty for a new profile ("Try searching to get started"). A person might think it is broken. Consider a hint or a default search.
- The Wikipedia donation pop-up covers part of the page on every visit. That is the site, not LLM OS, but the screen is crowded at this size.
- The Firefox opening animation, first load and YouTube start-up take about 6 to 10 s. Within the 30 s limit, but slow to a first-time user.
- Timings: open wikipedia reply 3 s; bbc.com about 5 s to show; DuckDuckGo search reply 3 s; YouTube home about 10 s to finish; YouTube search results about 6 s; video started within about 8 s of the click; close-browser reply 3 s; go-back reply 2 s.
- No pages failed to load. No crash. Browser closed fully with its X and with "close the browser".
