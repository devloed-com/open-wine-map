import json
items = json.load(open('tmp/it-consorzio-items.json'))
consorzi={c['id']:c for c in items['consorzi']}
add=json.load(open('tmp/it-consorzio-staged-additions.json'))
nolink=json.load(open('tmp/it-consorzio-no-link.json'))

# distinct found orgs/urls
orgs={}
for slug,v in add.items():
    orgs.setdefault((v['label'],v['url']),[]).append(slug)

L=[]
L.append("# Research results — IT consorzio / DO-organisation URLs\n")
L.append("Gap type: `it-consorzio-url` (free-form). Dispatched 2026-05-21 via 17 "
         "general-purpose research agents (WebSearch+WebFetch) + 1 cleanup agent.\n")
L.append("## Summary\n")
L.append(f"- 131 distinct consorzi researched: **117 FOUND**, 14 NONE.")
L.append(f"- 224 wines with no eAmbrosia consorzio: **60 FOUND**, 163 NONE, 1 UNREACHABLE.")
L.append(f"- **344 / 531 appellations** get a card link; 187 get none.")
L.append(f"- Distinct organisation websites: {len(orgs)}.\n")
L.append("## FOUND — appellation slug -> organisation | URL\n")
L.append("Grouped by organisation (one URL covers all listed slugs).\n")
for (label,url),slugs in sorted(orgs.items()):
    L.append(f"### {label}")
    L.append(f"  {url}")
    L.append(f"  slugs ({len(slugs)}): {', '.join(sorted(slugs))}\n")
L.append("## NO LINK — 187 appellations (-> CURATOR_TODO)\n")
for r in nolink:
    L.append(f"  {r['slug']} | {r['kind']} {r['name']} | {r['note']}")
open('tmp/it-consorzio-urls-research-results.md','w').write('\n'.join(L)+'\n')
print('wrote tmp/it-consorzio-urls-research-results.md')
print('distinct organisation websites:', len(orgs))
# verify-list
print()
print('JUDGEMENT CALLS flagged for review:')
print(' - Abruzzo consorzio: agents split between consorzio-viniabruzzo.it and')
print('   vinidabruzzo.it; staged with consorzio-viniabruzzo.it for all 7 Abruzzo slugs.')
print(' - colli-martani -> umbriatopwines.it (regional portal page, not the')
print('   consorzio\\'s own homepage). Consorzio has no standalone site.')
print(' - carso -> Associazione Viticoltori del Carso (producers\\' association,')
print('   not a formal consorzio di tutela; no consorzio exists for Carso DOC).')
print(' - friuli-isonzo/annia/latisana -> UNI.DOC FVG union body (the dedicated')
print('   per-DOC consorzi are defunct/merged).')
