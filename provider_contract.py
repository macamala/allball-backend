"""Expected contract for a future paid news-provider adapter.

No provider is connected in Phase 3.1. When one is added, map provider
payloads into these shapes and persist through existing Article + ArticleMedia
models. Do not invent missing facts, quotes, images, or scores.

ArticleIn:
- external_id: provider story id / canonical URL (internal)
- title
- summary / deck
- body_text or blocks (paragraphs, optional subheadings, verified quotations)
- published_at
- sport / league (or enough evidence for existing classifiers)
- team_names (optional; team entity table still required later)

MediaIn:
- url
- media_type: image | video
- caption (public if provided by rights-cleared asset)
- credit / license (INTERNAL unless a license later requires public attribution)
- sort_order
- is_hero
- provider_media_id

StructuredStory (future AI writer input/output, no OpenAI call here):
- title
- deck
- blocks: [{type: paragraph|heading|quote|list|media_hint, ...}]
- media_placement: optional indexes into ArticleMedia
- source_facts: verified factual material only
"""
