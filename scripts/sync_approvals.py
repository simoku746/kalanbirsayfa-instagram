"""İzleme Odası onaylarını kuyruğa işler.
usage: python3 scripts/sync_approvals.py <reviews_dir>
<reviews_dir>: ArtifactData 'list' (collection 'reviews', out_dir) çıktısı; içinde reviews/<slug>.json dosyaları olur.
Kural: review.approved_md5 == queue/<slug>/1.mp4'un md5'i ise APPROVED yazılır; onay geri alındıysa ya da video
değiştiyse APPROVED silinir. Değişiklik olduysa çıktının son satırı CHANGED olur (commit/push çağıran yapar)."""
import json, hashlib, os, sys, glob
Q = os.path.join(os.path.dirname(__file__), '..', 'queue')
docs = {}
for f in glob.glob(os.path.join(sys.argv[1], '**', '*.json'), recursive=True):
    try:
        d = json.load(open(f)); d = d.get('data', d)
        if d.get('slug'): docs[d['slug']] = d
    except Exception as e: print('okunamadı', f, e)
changed = []
for slug in sorted(os.listdir(Q)):
    pj = os.path.join(Q, slug, 'post.json')
    if not os.path.exists(pj): continue
    vid = os.path.join(Q, slug, json.load(open(pj)).get('files', ['1.mp4'])[0])
    if not os.path.exists(vid): continue
    md5 = hashlib.md5(open(vid, 'rb').read()).hexdigest(); ap = os.path.join(Q, slug, 'APPROVED')
    cur = open(ap).read().strip() if os.path.exists(ap) else None
    r = docs.get(slug)
    if r is not None and r.get('approved_md5') == md5:
        if cur != md5: open(ap, 'w').write(md5); changed.append('+' + slug)
    elif cur and (cur != md5 or (r is not None and not r.get('approved_md5'))):
        os.remove(ap); changed.append('-' + slug)
print('degisiklik:', ' '.join(changed) or 'yok')
if changed: print('CHANGED')
