# dev.to publishing instructions

The long-form article on dev.to is **the manifesto in
[`manifesto-multi-agent-local.md`](manifesto-multi-agent-local.md)**.
Copy the body of that file verbatim into the dev.to editor. This file
holds dev.to-specific metadata only — it is not the article body.

The rationale for consolidating: maintaining two parallel long-form drafts
drifts in voice and dilutes the manifesto's role as the canonical source
for every downstream piece of copy (README hero, Show HN, KOL DMs, AEO
posts). One source, multiple channels.

## Title

`Multi-agent AI coding belongs on your laptop`

Use the manifesto's title directly. Keyword-dense for organic search
("multi-agent", "AI coding", "laptop" implies local).

## Subtitle / dek

`Why the next generation of AI coding workflows is local-first and
model-pluralist — and what that means for your toolchain.`

## Tags (dev.to allows up to 4)

`ai`, `claudecode`, `multiagent`, `opensource`

Rationale:
- `ai` — broad reach within dev.to's AI vertical
- `claudecode` — searched by the highest-intent audience for ait
- `multiagent` — owns the differentiation
- `opensource` — gets the OSS-first crowd that hates SaaS

## Canonical URL

Set the canonical URL in dev.to to point at the article on your personal
blog or the `ait` docs site, not at dev.to itself. SEO juice should
accumulate on the domain you control.

## Cover image

1000x420 png, black background, white text:

```
ait — multi-agent AI coding,
                  on your laptop
```

Save to `assets/devto-cover.png` and upload as the cover in the dev.to
editor. Reuse for Hashnode and Medium mirrors.

## Publishing checklist

- [ ] `ait demo` shipped (Task #1) — manifesto CTA references it
- [ ] `[DOGFOOD-EVIDENCE]` placeholder in manifesto replaced with the real
      bug story from Task #2
- [ ] Article published on personal blog first; dev.to + Hashnode mirror
      with canonical URL pointing back to the personal blog
- [ ] Post-publish: cross-link from README, GitHub Discussions, and any
      existing release notes
- [ ] Submit to Lobsters (`open-source`, `ai`, `programming` tags) 48
      hours after dev.to to avoid same-day double-spend
- [ ] Tweet the manifesto in a 6-tweet thread (see Task #8 — separate file)
- [ ] After 7 days, write a short "what happened after I posted this"
      retrospective. The retro itself becomes a second piece of content.
