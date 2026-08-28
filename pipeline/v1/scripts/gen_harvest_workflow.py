"""Generate the CNRS-page harvest Workflow: one Haiku agent per (institution, year, scheme) group,
each fetching that institution's annual ERC-laureate page and extracting labs for the group's grants.
Embeds data (LF, ascii). Output flattens to one {grant_id, resolved_lab, ...} per grant."""
import os
import sys
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lib_erc

lib_erc.setup_stdout()
in_json = sys.argv[1] if len(sys.argv) > 1 else "outputs/harvest_groups.json"
out_js = sys.argv[2] if len(sys.argv) > 2 else "workflows/harvest.workflow.js"

_CTRL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def clean(v):
    if isinstance(v, str):
        return _CTRL.sub(" ", v).strip()
    if isinstance(v, dict):
        return {k: clean(x) for k, x in v.items()}
    if isinstance(v, list):
        return [clean(x) for x in v]
    return v


groups = clean(json.load(open(in_json, encoding="utf-8")))
embedded = json.dumps(groups, ensure_ascii=True)

js = '''// AUTO-GENERATED harvest — one agent per (institution, year, scheme) annual ERC page.
export const meta = {
  name: 'harvest-erc-labs',
  description: 'Batch-resolve RTO-hosted ERC grants from institutional annual laureate pages (Haiku)',
  phases: [{ title: 'Harvest' }],
}
const SCHEMA = {
  type: 'object', additionalProperties: false, required: ['results'],
  properties: {
    results: {
      type: 'array',
      items: {
        type: 'object', additionalProperties: false,
        required: ['grant_id', 'resolved_lab', 'tutelles', 'city', 'confidence', 'source_url'],
        properties: {
          grant_id: { type: 'string' }, resolved_lab: { type: ['string', 'null'] },
          tutelles: { type: 'array', items: { type: 'string' } }, city: { type: ['string', 'null'] },
          confidence: { type: 'number' }, source_url: { type: ['string', 'null'] },
        },
      },
    },
  },
}
const groups = __GROUPS__
const prompt = (g) => {
  const list = g.grants.map((x) => `- ${x.acronym} (id ${x.grant_id})${x.panel ? ' [' + x.panel + ']' : ''}`).join('\\n')
  return `${g.inst_short} ERC ${g.scheme} ${g.year} laureates — find each grant's actual French lab.
These ${g.grants.length} ERC grants are hosted by ${g.institution} (${g.scheme}, call year ${g.year}):
${list}

For each, identify the actual French research lab (UMR/unite) where the PI works — NOT the employer ${g.inst_short} — plus its tutelles/cotutelles and city. PRIMARY source: ${g.inst_short}'s official annual ERC-laureate announcement for ${g.year} ${g.scheme} (search e.g. "${g.inst_short} ERC ${g.scheme} ${g.year} laureats" or "ERC ${g.scheme} ${g.year} ${g.inst_short}"); that page usually lists all laureates at once. Use at most 3 web actions total for the whole group.

Return ONLY JSON {"results":[{"grant_id":"...","resolved_lab":"<lab>","tutelles":["<inst>"],"city":"<city>","confidence":<0-1>,"source_url":"<url>"}]} with one entry per grant above (match by id). If a grant is not found on the page, set its resolved_lab=null, confidence<=0.3.`
}
const out = await parallel(groups.map((g) => () =>
  agent(prompt(g), {
    label: `harvest:${g.inst_short}-${g.year}-${g.scheme}`, phase: 'Harvest',
    agentType: 'general-purpose', model: 'haiku', effort: 'low', schema: SCHEMA,
  }).then((r) => (r && r.results ? r.results.map((x) => ({ ...x, source_tier: 'cnrs-page' })) : []))
))
return out.filter(Boolean).flat()
'''.replace("__GROUPS__", embedded)

os.makedirs(os.path.dirname(out_js), exist_ok=True)
open(out_js, "w", encoding="utf-8", newline="\n").write(js)
n_grants = sum(len(g["grants"]) for g in groups)
print(f"wrote {out_js}: {len(groups)} groups ({n_grants} grants) ({len(js)//1024} KB)")
