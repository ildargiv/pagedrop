---
name: pagedrop
description: Builds a website from a short description and publishes it to GitHub Pages, then returns the live URL. Also updates a published site and connects a custom domain. Use when the user wants to "make a site and put it online", "publish to GitHub Pages", "deploy my landing page", "get a link I can share", or change a site published this way.
---

# PageDrop

From an idea to a live URL in one conversation. You write the site; `scripts/publish.py` creates the GitHub repository, turns on GitHub Pages, waits for the build, and confirms the link opens.

## Workflow

### 1. Brief — one message, at most three questions

Ask only what the request does not already say:

1. **The site and its one goal.** Who is it for, and what should a visitor do? (Book, buy, call, read, apply.)
2. **Real content.** Name, offer, prices, address, contacts, links, photos. Use only what the user gives you. Never invent testimonials, clients, awards, or numbers; use obvious placeholders like `[phone]` instead.
3. **Repository name.** It becomes the address: `<user>.github.io/<repo>/`. Suggest one (short, lowercase, hyphens).

If everything is already there, skip the questions and build.

### 2. Build

Create a new folder named after the repository, with a self-contained `index.html` (CSS and JS inline; images either from the user or from Unsplash with credit).

Quality bar — a page a good studio would sign:
- One clear idea on the first screen, a confident headline, and the primary action visible without scrolling.
- A deliberate palette (2–3 colors plus neutrals) and a type pairing from Google Fonts that supports the page's language.
- Responsive from 360px to wide screens; nothing scrolls sideways.
- `<title>`, `meta description`, `og:title`, `og:description`, alt text, semantic tags.
- `prefers-reduced-motion` respected; content visible without JavaScript.

**If the user wants motion design** ("animated", "wow", "like Apple") and the `motion-site` skill is installed, follow it for the build and its review loop. Otherwise keep animation tasteful: soft reveals on scroll, no bounces or particles.

### 3. Check before publishing

Open the page with whatever browser tool the session has (or `scripts/frames.py` from motion-site, if installed) at desktop width and at 390px. Fix console errors, horizontal scroll, broken images, and unreadable text before going further.

### 4. Publish

Publishing creates a **public** repository on the user's GitHub account. Unless the user already clearly asked to publish, confirm the repository name and that it will be public. Then run:

```bash
python scripts/publish.py <folder> --repo <name> --description "<one line about the site>"
```

The script:
- finds credentials on its own (`GITHUB_TOKEN`, `gh auth token`, or the git credential manager) and never prints them;
- refuses to overwrite an existing repository unless `--update` is passed;
- refuses to touch a folder whose git `origin` points somewhere else;
- creates the repo, pushes, enables Pages, waits for the build, and checks the URL returns 200;
- prints a JSON summary as its last line: `{"status": "live", "url": ..., "repo": ...}`.

If it reports no credentials, ask the user to run `gh auth login` or set `GITHUB_TOKEN` (a fine-grained token with Administration, Contents, and Pages read/write). Never ask them to paste a token into the chat.

### 5. Verify and report

When the status is `live`, open the URL yourself and confirm the real page loads (not a 404 or an old version). Then give the user:
- the live URL and the repository URL;
- one line on how to change it: "just tell me what to change";
- an honest note on anything you used as a placeholder.

If the status is not `live`, say exactly that — the push worked, and the site usually appears within a few minutes — and check again before claiming success.

## Updating a published site

Edit the files in the same folder, then:

```bash
python scripts/publish.py <folder> --repo <name> --update
```

If the original folder is gone, clone the repository first (`git clone https://github.com/<user>/<repo>.git`), edit, and publish with `--update`. Every publish is a commit, so any version can be restored from the git history.

## Custom domain

```bash
python scripts/publish.py <folder> --repo <name> --update --domain www.example.com
```

The script writes the `CNAME` file, sets the domain in Pages, and prints the DNS records the user must add at their registrar: four `A` records for an apex domain, or a `CNAME` to `<user>.github.io` for a subdomain. HTTPS turns on automatically once DNS resolves, which can take up to a day.

## Limits to tell the user about when relevant

- GitHub Pages hosts static sites: no server code, databases, or user accounts. Forms need a third-party service (e.g. Formspree) or a `mailto:` link.
- Free Pages requires a public repository. Never put private data in the site or the repo.
- Pages has soft limits (1 GB site, 100 GB/month bandwidth) that a normal site never reaches.
