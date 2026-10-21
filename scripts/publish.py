"""Paylaşım sırasından (queue/) zamanı gelen en eski gönderiyi Instagram'a (ve isteğe bağlı Facebook'a) paylaşır.
Env: IG_TOKEN, IG_USER_ID (vars. "me"), MEDIA_BASE_URL, FB_PAGE_ID/FB_PAGE_TOKEN (isteğe bağlı), DRY_RUN=1, IG_API_VERSION.
Kullanım: python3 scripts/publish.py | python3 scripts/publish.py check"""
import datetime as dt, json, os, pathlib, sys, time, urllib.error, urllib.parse, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
QUEUE = ROOT / 'queue'
TOKEN = os.environ.get('IG_TOKEN', '').strip()
UID = os.environ.get('IG_USER_ID', '').strip() or 'me'
BASE = os.environ.get('MEDIA_BASE_URL', '').rstrip('/')
VER = os.environ.get('IG_API_VERSION', '').strip('/')
API = 'https://graph.instagram.com' + (f'/{VER}' if VER else '')
DRY = os.environ.get('DRY_RUN') == '1'
TZ_SAAT = 3  # Türkiye (UTC+3)


def now_local():
    return dt.datetime.utcnow() + dt.timedelta(hours=TZ_SAAT)


def due_at(post):
    return dt.datetime.fromisoformat(f"{post['date']}T{post.get('time', '12:30')}")


def call(method, path, **params):
    if DRY:
        print('DRY', method, path, {k: v for k, v in params.items() if k != 'caption'})
        return {'id': 'dry', 'status_code': 'FINISHED', 'data': []}
    params['access_token'] = TOKEN
    data = urllib.parse.urlencode(params).encode()
    url = f'{API}/{path}'
    req = urllib.request.Request(url + ('?' + data.decode() if method == 'GET' else ''),
                                 data=None if method == 'GET' else data, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        msg = f'Instagram API error {e.code} on {method} {path}: {e.read().decode("utf-8", "replace")}'
        print(f'::error::{msg}')
        raise SystemExit(msg)


def wait_ready(cid, timeout=900):
    t0 = time.time()
    while True:
        st = call('GET', cid, fields='status_code').get('status_code')
        if st == 'FINISHED':
            return
        if st in ('ERROR', 'EXPIRED'):
            raise SystemExit(f'Container {cid} failed: {st}')
        if time.time() - t0 > timeout:
            raise SystemExit(f'Container {cid} not ready after {timeout}s')
        time.sleep(10)


def url_for(folder, name):
    rel = folder.relative_to(ROOT).as_posix()
    return f'{BASE}/{urllib.parse.quote(rel)}/{urllib.parse.quote(name)}'


def publish(folder, post):
    kind, files, cap = post['type'], post['files'], post.get('caption', '')
    if kind == 'image':
        cid = call('POST', f'{UID}/media', image_url=url_for(folder, files[0]), caption=cap)['id']
    elif kind == 'carousel':
        if not 2 <= len(files) <= 10:
            raise SystemExit('carousel needs 2-10 files')
        kids = [call('POST', f'{UID}/media', image_url=url_for(folder, f), is_carousel_item='true')['id'] for f in files]
        for k in kids:
            wait_ready(k)
        cid = call('POST', f'{UID}/media', media_type='CAROUSEL', children=','.join(kids), caption=cap)['id']
    elif kind == 'reel':
        p = dict(media_type='REELS', video_url=url_for(folder, files[0]), caption=cap, share_to_feed='true')
        if post.get('cover'):
            p['cover_url'] = url_for(folder, post['cover'])
        cid = call('POST', f'{UID}/media', **p)['id']
    else:
        raise SystemExit(f'unknown type {kind}')
    wait_ready(cid)
    return call('POST', f'{UID}/media_publish', creation_id=cid).get('id')


def already_posted(post):
    """Çift paylaşım koruması: aynı açıklama son 48 saatte paylaşılmışsa True."""
    cap = (post.get('caption') or '').strip()[:120]
    if not cap:
        return False
    sinir = dt.datetime.utcnow() - dt.timedelta(hours=48)
    for m in call('GET', f'{UID}/media', fields='caption,timestamp', limit='15').get('data', []):
        ts = dt.datetime.strptime(m['timestamp'][:19], '%Y-%m-%dT%H:%M:%S')
        if ts >= sinir and (m.get('caption') or '').strip()[:120] == cap:
            return True
    return False


# ---- Facebook Sayfası (isteğe bağlı) ----
FB_PAGE = os.environ.get('FB_PAGE_ID', '').strip()
FB_TOKEN = os.environ.get('FB_PAGE_TOKEN', '').strip()
FB_API = 'https://graph.facebook.com/' + (VER or 'v23.0')


def fb_call(path, **params):
    params['access_token'] = FB_TOKEN
    req = urllib.request.Request(f'{FB_API}/{path}', data=urllib.parse.urlencode(params).encode(), method='POST')
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        raise RuntimeError(f'Facebook API error {e.code} on {path}: {e.read().decode("utf-8", "replace")}')


def publish_fb(folder, post):
    kind, files, cap = post['type'], post['files'], post.get('caption', '')
    if kind == 'image':
        return fb_call(f'{FB_PAGE}/photos', url=url_for(folder, files[0]), message=cap).get('post_id')
    if kind == 'carousel':
        ids = [fb_call(f'{FB_PAGE}/photos', url=url_for(folder, f), published='false')['id'] for f in files]
        media = {f'attached_media[{i}]': json.dumps({'media_fbid': x}) for i, x in enumerate(ids)}
        return fb_call(f'{FB_PAGE}/feed', message=cap, **media).get('id')
    if kind == 'reel':
        return fb_call(f'{FB_PAGE}/videos', file_url=url_for(folder, files[0]), description=cap).get('id')


def check():
    me = call('GET', 'me', fields='user_id,username,account_type,followers_count,media_count')
    print(f"::notice::Bağlantı tamam: @{me.get('username')} ({me.get('account_type')}) · "
          f"takipçi {me.get('followers_count')} · gönderi {me.get('media_count')}")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == 'check':
        return check()
    if not DRY and (not TOKEN or not BASE):
        raise SystemExit('IG_TOKEN and MEDIA_BASE_URL must be set')
    due = []
    for d in (sorted(p for p in QUEUE.iterdir() if p.is_dir()) if QUEUE.exists() else []):
        f = d / 'post.json'
        if f.exists():
            post = json.loads(f.read_text(encoding='utf-8'))
            if due_at(post) <= now_local():
                due.append((d, post))
    due.sort(key=lambda x: (due_at(x[1]), x[0].name))
    if not due:
        print('Nothing due.')
        return
    folder, post = due[0]
    out = os.environ.get('GITHUB_OUTPUT')
    if not DRY and already_posted(post):
        print(f'::warning::{folder.name} zaten paylaşılmış; tekrar paylaşılmadı.')
        if out:
            open(out, 'a').write(f'folder={folder.name}\nmedia_id=zaten-paylasilmis\n')
        return
    media_id = publish(folder, post)
    print(f'PUBLISHED {folder.name} -> media {media_id}')
    if FB_PAGE and FB_TOKEN:
        try:
            print(f'::notice::Facebook: {publish_fb(folder, post)}')
        except Exception as e:   # Instagram geçerli; Facebook hatası işi durdurmasın
            print(f'::warning::Facebook paylaşımı başarısız: {str(e)[:400]}')
    if out:
        open(out, 'a').write(f'folder={folder.name}\nmedia_id={media_id}\n')


if __name__ == '__main__':
    main()
