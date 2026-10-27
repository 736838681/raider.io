#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Raider.IO official public API only. Python >= 3.9, no third-party packages."""
from __future__ import annotations
import argparse
import csv
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

API = 'https://raider.io/api/v1'
SLOTS = [('head','头'), ('shoulder','肩'), ('chest','胸'), ('back','背'),
         ('wrist','腕'), ('hands','手'), ('waist','腰'), ('legs','腿'), ('feet','脚')]
# All tank-to-DPS combinations from the same class.
PAIRS = [
 ('death-knight','blood','frost','鲜血DK＋冰霜DK'),
 ('death-knight','blood','unholy','鲜血DK＋邪恶DK'),
 ('warrior','protection','arms','防护战士＋武器战士'),
 ('warrior','protection','fury','防护战士＋狂怒战士'),
 ('paladin','protection','retribution','防护骑士＋惩戒骑士'),
 ('demon-hunter','vengeance','havoc','复仇DH＋浩劫DH'),
 ('demon-hunter','vengeance','devourer','复仇DH＋噬灭DH'),
 ('monk','brewmaster','windwalker','酒仙武僧＋踏风武僧'),
 ('druid','guardian','balance','守护德鲁伊＋平衡德鲁伊'),
 ('druid','guardian','feral','守护德鲁伊＋野性德鲁伊'),
]
EXPECTED = {(c,s) for c,t,d,_ in PAIRS for s in (t,d)}
SPEC_ALIAS = {'blood':'blood', 'frost':'frost', 'unholy':'unholy', 'arms':'arms',
 'fury':'fury','protection':'protection','retribution':'retribution',
 'vengeance':'vengeance','havoc':'havoc','devourer':'devourer',
 'brewmaster':'brewmaster','windwalker':'windwalker','guardian':'guardian',
 'balance':'balance','feral':'feral', '噬灭':'devourer','吞噬':'devourer'}
CLASS_ALIAS = {'deathknight':'death-knight','death knight':'death-knight',
 'demonhunter':'demon-hunter','demon hunter':'demon-hunter',
 'warrior':'warrior','paladin':'paladin','monk':'monk','druid':'druid',
 '死亡骑士':'death-knight','战士':'warrior','圣骑士':'paladin',
 '恶魔猎手':'demon-hunter','德鲁伊':'druid','武僧':'monk'}


def norm_class(value):
    v = slug_str(value)
    return CLASS_ALIAS.get(v, v)


def norm_spec(value):
    v = slug_str(value)
    return SPEC_ALIAS.get(v, v)


def slug_str(value):
    if isinstance(value, dict):
        for key in ('slug','name','key','short_name','code'):
            if value.get(key):
                return slug_str(value[key])
        return ''
    return str(value or '').strip().lower().replace('_','-')


def plain(value):
    if isinstance(value, dict):
        for k in ('slug','name','title','code','region'):
            if value.get(k):
                return str(value[k])
        return ''
    return str(value or '')


def num(value, default=0):
    try:
        return float(value)
    except (ValueError, TypeError):
        return default


class APIClient:
    def __init__(self, delay=0.7, timeout=20, retries=3):
        self.delay = delay
        self.timeout = timeout
        self.retries = retries
        self.last_time = 0.0
        self.total = 0
    def get(self, route, params):
        url = API + route + '?' + urllib.parse.urlencode(params)
        for attempt in range(self.retries + 1):
            pause = max(0, self.delay - (time.monotonic() - self.last_time))
            if pause:
                time.sleep(pause)
            self.last_time = time.monotonic()
            self.total += 1
            req = urllib.request.Request(url, headers={
                'Accept':'application/json',
                'User-Agent':'RIOArmorComparison/1.0 (personal research; public API)'})
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as response:
                    return json.load(response)
            except urllib.error.HTTPError as exc:
                if exc.code in (429, 500, 502, 503, 504) and attempt < self.retries:
                    header = exc.headers.get('Retry-After', '')
                    try:
                        wait = min(180, max(float(header), 1.0))
                    except ValueError:
                        wait = min(60, 2 ** (attempt + 1))
                    print('  HTTP', exc.code, 'retry after', wait, 'sec', flush=True)
                    time.sleep(wait)
                    continue
                raise RuntimeError('HTTP %s: %s'%(exc.code, url)) from exc
            except (urllib.error.URLError, TimeoutError) as exc:
                if attempt < self.retries:
                    time.sleep(2 ** (attempt + 1))
                    continue
                raise RuntimeError('Network error: %s; %s'%(exc, url)) from exc
            except json.JSONDecodeError as exc:
                raise RuntimeError('API did not return valid JSON: %s'%url) from exc
        raise AssertionError('unreachable')


def pick_run(entry):
    if not isinstance(entry, dict):
        return None
    return entry.get('run') if isinstance(entry.get('run'),dict) else entry


def extract_rankings(payload):
    if isinstance(payload,list):
        return payload
    if not isinstance(payload,dict):
        return []
    for key in ('rankings','runs'):
        if isinstance(payload.get(key), list):
            return payload[key]
    return []


def read_member(member, default_region, score):
    if not isinstance(member,dict):
        return None
    ch = member.get('character') if isinstance(member.get('character'),dict) else member
    name = plain(ch.get('name')).strip()
    realm = plain(ch.get('realm')).strip()
    region = slug_str(ch.get('region') or default_region)
    if region not in ('us','eu','kr','tw','cn'):
        region = default_region
    c = norm_class(ch.get('class') or ch.get('class_name'))
    s = norm_spec(ch.get('spec') or member.get('spec'))
    if not name or not realm or (c,s) not in EXPECTED:
        return None
    return {'region':region, 'realm':realm, 'name':name, 'class':c,
            'spec':s, 'source_score':float(score), 'source':'runs'}


def run_candidates(client, season, regions, pages, warnings):
    all_users = {}
    stats = Counter()
    for region in regions:
        for page in range(pages):
            print('[Runs]',region,'page',page,'/',pages - 1,flush=True)
            try:
                raw = client.get('/mythic-plus/runs', {
                  'season':season,'region':region,'dungeon':'all','affixes':'all','page':page})
            except Exception as exc:
                warnings.append(['排行榜','%s page %s'%(region,page),str(exc)])
                break
            rows = extract_rankings(raw)
            if page == 0 and not rows:
                warnings.append(['排行榜','%s page 0'%region,
                    'API response contains no rankings; fields='+(','.join(raw) if isinstance(raw,dict) else str(type(raw)))])
            if not rows:
                break
            stats[region] += len(rows)
            for row in rows:
                run = pick_run(row)
                if not run:
                    continue
                score = num(run.get('score') or row.get('score'))
                roster = run.get('roster') or []
                if not isinstance(roster,list):
                    continue
                for member in roster:
                    p = read_member(member, region, score)
                    if not p:
                        continue
                    key = (p['region'],p['realm'].lower(),p['name'].casefold(),p['class'],p['spec'])
                    if key not in all_users or p['source_score'] > all_users[key]['source_score']:
                        all_users[key] = p
    return list(all_users.values()), stats


def read_manual(path):
    result = []
    with open(path,encoding='utf-8-sig',newline='') as f:
        for i,row in enumerate(csv.DictReader(f),2):
            region = row.get('region','').strip().lower()
            realm = row.get('realm','').strip()
            name = row.get('name','').strip()
            c = norm_class(row.get('class',''))
            s = norm_spec(row.get('spec',''))
            if region not in ('us','eu','kr','tw','cn') or not realm or not name or (c,s) not in EXPECTED:
                raise ValueError('名单CSV第%s行无效: %s'%(i,row))
            result.append({'region':region,'realm':realm,'name':name,'class':c,'spec':s,
                           'source_score':float(num(row.get('source_score'))), 'source':'manual'})
    return result


def dedup(players):
    best = {}
    for p in players:
        key = (p['region'],p['realm'].lower(),p['name'].casefold(),p['class'],p['spec'])
        if key not in best or p['source_score'] > best[key]['source_score']:
            best[key] = p
    return list(best.values())


def get_items(profile):
    gear = profile.get('gear')
    if not isinstance(gear,dict):
        return None
    raw = gear.get('items')
    if not isinstance(raw,dict):
        return None
    result = {}
    for slot,_ in SLOTS:
        aliases = {'hands':['hands','hand'], 'shoulder':['shoulder','shoulders'],
                   'legs':['legs','leg'], 'feet':['feet','foot']}
        item = next((raw[k] for k in [slot] + aliases.get(slot,[]) if isinstance(raw.get(k),dict)),None)
        if not item:
            continue
        ident = item.get('item_id') or item.get('id')
        try:
            ident = int(ident)
        except (ValueError,TypeError):
            continue
        result[slot] = {'id':ident, 'name':str(item.get('name') or ''),
                        'ilevel':item.get('item_level'), 'bonuses':item.get('bonuses',[])}
    return result


def profile_player(client,p):
    data = client.get('/characters/profile', {'region':p['region'], 'realm':p['realm'],
                                              'name':p['name'], 'fields':'gear'})
    active_spec = norm_spec(data.get('active_spec_name') or data.get('spec'))
    active_class = norm_class(data.get('class'))
    items = get_items(data)
    if active_spec != p['spec'] or (active_class and active_class != p['class']):
        raise ValueError('active spec/class mismatch: run=%s/%s; now=%s/%s'%(
            p['class'],p['spec'],active_class,active_spec))
    if not items or len(items) < len(SLOTS):
        raise ValueError('incomplete armor slots (%s/%s)'%(len(items or {}),len(SLOTS)))
    gear = data.get('gear') or {}
    p = p.copy()
    p['items'] = items
    p['gear_updated'] = gear.get('updated_at','')
    p['profile_url'] = data.get('profile_url') or 'https://raider.io/characters/%s/%s/%s'%(
        p['region'],urllib.parse.quote(p['realm']),urllib.parse.quote(p['name']))
    return p


def common_items(players):
    by_spec=defaultdict(list)
    for p in players:
        by_spec[(p['class'],p['spec'])].append(p)
    modes = {}
    for key,group in by_spec.items():
        by_slot={}
        for slot,_ in SLOTS:
            counts=Counter(p['items'][slot]['id'] for p in group)
            best_id, count=sorted(counts.items(),key=lambda e:(-e[1],e[0]))[0]
            item=next(p['items'][slot] for p in group if p['items'][slot]['id']==best_id)
            by_slot[slot]={'id':best_id,'name':item['name'],'uses':count,'sample':len(group)}
        modes[key]=by_slot
    return by_spec,modes


def summaries(players,min_samples):
    by_spec,modes=common_items(players) if players else ({},{})
    ranking=[]
    details=[]
    for c,t,d,label in PAIRS:
        a=by_spec.get((c,t),[])
        b=by_spec.get((c,d),[])
        valid=len(a)>=min_samples and len(b)>=min_samples
        matches=0
        for slot,zh in SLOTS:
            item_a=modes.get((c,t),{}).get(slot,{})
            item_b=modes.get((c,d),{}).get(slot,{})
            same=bool(item_a and item_b and item_a.get('id') == item_b.get('id'))
            matches+=int(same)
            details.append({'组合':label,'部位':zh,
                '坦克主流物品ID':item_a.get('id',''),'坦克装备':item_a.get('name',''),
                '坦克人数':item_a.get('uses',''),'坦克样本':len(a),
                '输出主流物品ID':item_b.get('id',''),'输出装备':item_b.get('name',''),
                '输出人数':item_b.get('uses',''),'输出样本':len(b),
                '物品ID相同':('是' if same else '否') if item_a and item_b else '数据不足',
                '是否纳入正式排序':('是' if valid else '否')})
        best_n=None
        if a and b:
            best_n=max(sum(x['items'][slot]['id']==y['items'][slot]['id'] for slot,_ in SLOTS)
                       for x in a for y in b)
        ranking.append({'组合':label,'相同防具件数_主流ID':matches if valid else '',
              '总部位':9,'坦克样本数':len(a),'输出样本数':len(b),
              '实测玩家两两最高重合数_仅参考':best_n if valid else '',
              '状态':'有效样本' if valid else '样本不足_不排名'})
    ranking.sort(key=lambda r:(r['状态']!='有效样本',-(r['相同防具件数_主流ID'] or -1),r['组合']))
    return ranking,details,by_spec


def csv_out(path,rows,headers):
    with open(path,'w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=headers,extrasaction='ignore')
        w.writeheader()
        w.writerows(rows)


def main(argv=None):
    parser=argparse.ArgumentParser(description='Compare 9 armor slot IDs between tank and DPS players via official Raider.IO API')
    parser.add_argument('--season',default='season-mn-2')
    parser.add_argument('--regions',default='us,eu,kr,tw,cn')
    parser.add_argument('--pages',type=int,default=8,help='top 20 run entries per page and region')
    parser.add_argument('--per-spec',type=int,default=12)
    parser.add_argument('--min-samples',type=int,default=3)
    parser.add_argument('--delay',type=float,default=0.7)
    parser.add_argument('--roster-file',default='',help='Optional CSV: region,realm,name,class,spec,source_score')
    parser.add_argument('--manual-only',action='store_true',help='Do not fetch runs; use roster-file only')
    parser.add_argument('--out',default='结果')
    parser.add_argument('--test-api',action='store_true',help='Only test Raider.IO connectivity')
    args=parser.parse_args(argv)
    if args.pages<1 or args.pages>101 or args.per_spec<1 or args.min_samples<1 or args.delay<0.3:
        parser.error('pages 1..101; per-spec>=1; min-samples>=1; delay>=0.3')
    regions=[s.strip().lower() for s in args.regions.split(',') if s.strip()]
    if any(r not in ('us','eu','kr','tw','cn','world') for r in regions):
        parser.error('region must be us,eu,kr,tw,cn,world')
    client=APIClient(delay=args.delay)
    out=Path(args.out)
    out.mkdir(parents=True,exist_ok=True)
    warnings=[]
    if args.test_api:
        data=client.get('/mythic-plus/runs',{'season':args.season,'region':'cn','page':0})
        print('Connected. China page rankings:',len(extract_rankings(data)))
        print('Available top-level fields:',list(data) if isinstance(data,dict) else type(data))
        return 0
    players=[]
    stats=Counter()
    if not args.manual_only:
        players,stats=run_candidates(client,args.season,regions,args.pages,warnings)
    if args.roster_file:
        players+=read_manual(args.roster_file)
    players=dedup(players)
    groups=defaultdict(list)
    for p in players:
        groups[(p['class'],p['spec'])].append(p)
    selected=[]
    for key,group in groups.items():
        selected+=sorted(group,key=lambda p:p['source_score'],reverse=True)[:args.per_spec]
    selected.sort(key=lambda p:(p['class'],p['spec'],-p['source_score']))
    print('Discovered',len(players),'unique spec-character records; selected',len(selected),flush=True)
    ok=[]
    for i,p in enumerate(selected,1):
        print('[Gear %s/%s]'%(i,len(selected)),p['region'],p['name'],p['class'],p['spec'],flush=True)
        try:
            ok.append(profile_player(client,p))
        except Exception as exc:
            warnings.append(['装备','%s/%s/%s (%s %s)'%(
                p['region'],p['realm'],p['name'],p['class'],p['spec']),str(exc)])
    ranking,details,by_spec=summaries(ok,args.min_samples)
    csv_out(out/'01_重合件数排序.csv',ranking,[
        '组合','相同防具件数_主流ID','总部位','坦克样本数','输出样本数',
        '实测玩家两两最高重合数_仅参考','状态'])
    csv_out(out/'02_九个部位逐件核对.csv',details,[
        '组合','部位','坦克主流物品ID','坦克装备','坦克人数','坦克样本',
        '输出主流物品ID','输出装备','输出人数','输出样本','物品ID相同','是否纳入正式排序'])
    itemrows=[]
    for p in ok:
        for slot,zh in SLOTS:
            it=p['items'][slot]
            itemrows.append({'region':p['region'],'realm':p['realm'],'name':p['name'],
                'class':p['class'],'spec':p['spec'],'run_score':p['source_score'],
                'slot':zh,'item_id':it['id'],'item_name':it['name'],
                'item_level':it['ilevel'],'profile_url':p['profile_url'],
                'gear_updated':p['gear_updated']})
    csv_out(out/'03_全部玩家装备明细.csv',itemrows,[
        'region','realm','name','class','spec','run_score','slot','item_id',
        'item_name','item_level','profile_url','gear_updated'])
    csv_out(out/'04_接口失败和排除原因.csv',[
        {'类型':a,'对象':b,'原因':c} for a,b,c in warnings],['类型','对象','原因'])
    cover=[]
    for c,s in sorted(EXPECTED):
        group=by_spec.get((c,s),[])
        cover.append({'class':c,'spec':s,'成功且9件齐全':len(group),
                     '国服成功':sum(p['region']=='cn' for p in group),
                     '其他区域成功':sum(p['region']!='cn' for p in group)})
    csv_out(out/'05_专精及国服覆盖.csv',cover,['class','spec','成功且9件齐全','国服成功','其他区域成功'])
    valid=sum(1 for x in ranking if x['状态']=='有效样本')
    report=[
        '数据生成UTC: '+datetime.now(timezone.utc).isoformat(),
        '数据来源: https://raider.io/api 公开API /mythic-plus/runs 和 /characters/profile?fields=gear',
        '赛季: '+args.season,
        '候选选择: 官方高层副本队伍成员；不是专精世界排名前N。每角色以采样副本最高分排序。',
        '从 runs 获取的各区域副本数: '+repr(dict(stats)),
        '筛选前角色-专精记录: '+str(len(players)),
        '尝试查询角色装备: '+str(len(selected)),
        '成功且满9防具、当前专精一致: '+str(len(ok)),
        '排除/请求失败: '+str(len(warnings)),
        '达到双专精最低样本数的组合: %s/10'%valid,
        '国服成功角色: '+str(sum(p['region']=='cn' for p in ok)),
        '统计口径: 每个专精、每个部位在样本中出现频率最高的 item_id 相等，计为该部位相同。',
        '不计入项链/戒指/武器/饰品。披风算防具。',
        '相同物品ID不保证同装等/绿字/附魔/宝石；结果不代表最优配装，不代表性能损失。',
        '角色gear是当前快照，不保证与高层通关当时相同。',
        '有样本不足时结果会空白而不是给出0件。',
        'Raider.IO 不允许在公开API以外自动批量抓取，本程序仅访问官方公开API。',
    ]
    with open(out/'00_先读我_统计说明.txt','w',encoding='utf-8-sig') as f:
        f.write('\n'.join(report)+'\n')
    print('\n'.join(report),flush=True)
    print('RESULT:',out.resolve(),flush=True)
    return 0 if ok else 2

if __name__=='__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print('Interrupted',file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print('ERROR:',e,file=sys.stderr)
        sys.exit(1)
