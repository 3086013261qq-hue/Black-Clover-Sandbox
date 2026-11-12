#!/usr/bin/env python3
# coding: utf-8
"""Build Black Clover chara_card_v3-compatible character_book from immutable sources.

Use: python assembly/scripts/build_worldbook.py
Writes only assembly/worldbook/dist/*.json. Does not edit source chapters or user preset.
"""
from __future__ import annotations
from collections import Counter
from copy import deepcopy
from datetime import date
import json
import math
from pathlib import Path
import re

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/"assembly/worldbook/dist"
LOC_MANIFESTS=sorted((ROOT/"worldbook/locations").glob("000_LOC-*_触发元数据候选_*.json"))
GREEN_MANIFESTS=sorted((ROOT/"worldbook/settings/green").glob("blue??/000_触发元数据候选_*.json"))
PART_DIR=ROOT/"assembly/worldbook/components"
VERSION="v1.0.0-assembly-rc1"
class BuildError(RuntimeError):pass
def assert_(condition,reason):
    if not condition:raise BuildError(reason)
def read(p):
    assert_(p.exists(),f"Missing source: {p.relative_to(ROOT)}")
    return p.read_text(encoding="utf-8").strip()
def source(rel):
    p=(ROOT/rel).resolve()
    assert_(p.is_relative_to(ROOT.resolve()),f"Unexpected path {rel}")
    return read(p)
def manifest(path):
    return json.loads(read(path))["entries"]
def canonical_ext(position="after_char",recursive=False):
    ext=dict(selectiveLogic=0,position={"before_char":0,"after_char":1,"at_depth":4}[position],
       depth=0 if position=="at_depth" else 4,role=0,match_whole_words=True,
       probability=100,useProbability=True,sticky=0,cooldown=0,delay=0,
       exclude_recursion=recursive,prevent_recursion=recursive,delay_until_recursion=False,
       group="",group_override=False,group_weight=100,use_group_scoring=False,
       scan_depth=2,case_sensitive=False,automation_id="",vectorized=False,
       display_index=0,outlet_name="",match_persona_description=False,
       match_character_description=False,match_character_personality=False,
       match_character_depth_prompt=False,match_scenario=False,
       match_creator_notes=False,triggers=[],ignore_budget=False)
    return ext
def entry(comment,content,order,keys=None,enabled=True,constant=False,position="after_char",recursive=False,use_regex=True):
    e=dict(keys=keys or [],secondary_keys=[],comment=comment,content=content,
      constant=constant,selective=True,insertion_order=order,enabled=enabled,
      position=position,use_regex=use_regex,
      extensions=canonical_ext(position,recursive))
    assert_(e["constant"] or len(e["keys"])>0,f"missing keys {comment}")
    return e
def marker(group,stage,order):
    return entry(f"【{group}:{stage}】","",order,constant=True)
def onefile(globpat,expected):
    matched=list(ROOT.glob(globpat))
    assert_(len(matched)==1,f"{globpat} -> {len(matched)} expected 1")
    return matched[0]
def name_from_character(body):
    m=re.search(r"<([^<>\n]+)character>",body)
    assert_(bool(m),"Malformed character tag")
    assert_(f"</{m.group(1)}character>" in body,"Character end tag missing")
    return m.group(1)
def scene_regex(aliases):
    p="|".join(re.escape(a) for a in aliases)
    return r"/<story_scene>(?:(?!<\/story_scene>)[\s\S])*?(?:"+p+r")(?:(?!<\/story_scene>)[\s\S])*?<\/story_scene>/s"
def position_regex(aliases,exclude=False):
    p="|".join(re.escape(a) for a in aliases)
    x=(r"(?![^\r\n<]*(?:黑桃王国王都|红心王国王都|钻石王国王都|魔法议会|裁判所|审判庭|法庭))" if exclude else "")
    return (r"/<status\b[^>]*>(?:(?!<\/status>)[\s\S])*?^[ \t]*(?:📍\s*)?当前位置[:：][ \t]*"+
      x+r"(?=[^\r\n<]*(?:"+p+r"))[^\r\n<]*(?=\r?$)(?:(?!<\/status>)[\s\S])*?<\/status>/m")
def rx(s):
    assert_(s.startswith("/") and s.rfind("/")>0,"Invalid regex delimiter")
    i=s.rfind("/")
    fl=re.M if "m" in s[i+1:] else 0
    if "s" in s[i+1:]:fl|=re.S
    return re.compile(s[1:i],fl)

# Stable scene aliases shared without difference by the corresponding CHAR and ABILITY.
special_aliases={
  "夜见介大":["夜见"],"尤利乌斯·诺瓦克罗诺":["尤利乌斯"],
  "梅列欧蕾欧娜·凡米利安":["梅列欧蕾欧娜"],
  "阿斯塔":["黑色暴牛阿斯塔"],"由诺":["金色黎明由诺"],
  "塞克蕾·斯瓦洛泰尔":["塞克蕾","尼禄"],
  "洛洛佩琪卡":["红心女王"],"纳哈特·浮士德":["纳哈特"],
  "卢修斯·佐格拉提斯":["卢修斯"],
}
def make_character_aliases(name,names):
    a=[name]
    if "·" in name and "（" not in name:
        part=name.split("·")[0]
        if len(part)>=2 and sum(other.split("·")[0]==part for other in names)==1:a.append(part)
    a+=special_aliases.get(name,[])
    return list(dict.fromkeys(a))

def build():
    parts=sorted(PART_DIR.glob("*.md"))
    assert_(len(parts)==6,"Missing six fullstack components")
    piece={p.name[:2]:read(p) for p in parts}
    assert_(sorted(piece)==["01","02","03","04","05","06"],"Component numbering")
    assert_(all("【待替换】" not in x for x in piece.values()),"Fullstack component placeholder")
    assert_(all(piece["01"].count("━━ "+str(i)+".")==1 for i in range(1,7)),"Combat six steps")
    assert_(piece["02"].count("<!-- 规则:")+piece["02"].count("<!-- 规则：")>=10,"Status field rules missing")
    assert_(piece["05"].count("[来源:")==12+1,"Topic count: expected 12 plus instruction")
    assert_(piece["03"].count(" -> ")>=10,"Worldcheck replacements")
    data=[]
    # Reset local globals, then three disabled memory storage slots.
    data.append(entry("🗑️清空局部变量(别关)",
       "{{setvar::combat_driver::}}\n{{setvar::status_format::}}\n"
       "{{setvar::世界书重大记忆存储::}}\n{{setvar::世界书日常记忆存储::}}\n"
       "{{setvar::世界书玩家身世背景::}}",556,constant=True,position="before_char"))
    data.append(marker("记忆相关","起始",555))
    memory=[
      ("日常记忆存储","世界书日常记忆存储","日期与事实：尚无已记录事项。",554),
      ("重大记忆存储","世界书重大记忆存储","重要事件与其后果：尚无已记录事项。",553),
      ("玩家身世背景","世界书玩家身世背景","<user>身世背景：由玩家设定与实际经历决定。",552)]
    for name,var,body,o in memory:
        data.append(entry(name,"{{setvar::"+var+"::\n"+body+"\n}}",o,enabled=False,constant=True))
    data.append(marker("记忆相关","结尾",551))
    data.append(marker("输出规则","起始",550))

    tls=sorted((ROOT/"worldbook/timeline").glob("TL-??_v4_*.md"))
    assert_(len(tls)==27,"Expected exactly 27 v4 timeline files")
    for i,p in enumerate(tls):
        n=int(p.name[3:5]);assert_(n==i+1,f"Timeline sequence gap {p}")
        body=read(p)
        assert_(body.startswith("<world_timeline>") and body.endswith("</world_timeline>"),"Timeline tag "+p.name)
        assert_(body.count("<world_timeline>")==1 and body.count("</world_timeline>")==1,"Merged TL "+p.name)
        assert_("-事件A:" in body and "沙盒模式" in body,"Missing event A or sandbox "+p.name)
        data.append(entry(f"时间线-第{n:02d}卷-{p.stem.split('_',2)[2]}(多选一)",body,480-i,enabled=(i==0),constant=True,position="at_depth"))
    data.append(entry("战斗思维链",piece["01"],453,constant=True,position="at_depth"))
    data.append(entry("状态栏-黑色四叶草",piece["02"],452,constant=True,position="at_depth"))
    data.append(marker("输出规则","结尾",451))
    data.append(marker("核心规则","起始",450))
    for code,comment,order in [
       ("06","核心规则:黑色四叶草阶段与沙盒锚定",406),
       ("05","开放性话题：黑色四叶草话题池",405),
       ("04","核心规则:黑色四叶草叙述与对白规范",404),
       ("03","核心规则:黑色四叶草世界观校验/过滤",403)]:
        data.append(entry(comment,piece[code],order,constant=True))
    data.append(marker("核心规则","结尾",401))

    data.append(marker("核心设定","起始",400))
    blue=sorted((ROOT/"worldbook/settings/blue").glob("BLUE-??_*.md"))
    assert_(len(blue)==8,"Expected exactly 8 BLUE")
    for i,p in enumerate(blue):
        assert_(int(p.name[5:7])==i+1,"BLUE id mismatch")
        data.append(entry("核心设定:蓝灯-"+p.stem[8:],read(p),399-i,constant=True))
    greens=[]
    for p in GREEN_MANIFESTS:greens+=manifest(p)
    assert_(len(GREEN_MANIFESTS)==8 and len(greens)==67,"Expected 8 manifests/67 GREEN")
    assert_(len(set(x["id"] for x in greens))==67,"Duplicate GREEN id")
    members=[]
    for i in range(1,129):
        id=f"{i:03d}"
        cp=onefile(f"worldbook/characters/CHAR-{id}_*.md",1)
        ap=onefile(f"worldbook/abilities/ABILITY-{id}_*.md",1)
        cb,ab=read(cp),read(ap)
        name=name_from_character(cb)
        assert_(ab.startswith("<核心设定:") and ab.rstrip().endswith(f"</核心设定:{name}·能力>"),"ABILITY tag "+id)
        members.append((i,name,cb,ab))
    assert_(len(members)==128,"Expected 128 paired characters & abilities")
    names=[x[1] for x in members]
    alias_by_id={i:make_character_aliases(name,names) for i,name,_,_ in members}
    scene_by_id={i:[scene_regex(alias_by_id[i])] for i in alias_by_id}
    # Core-setting entries have 98 available integer orders (399-302), and 203
    # source entries, so repeated integer orders are unavoidable; stable array
    # order and display_index are authoritative for equal-order entries.
    core_content=[]
    for g in greens:
        source_body=source(g["file"])
        assert_(source_body.startswith("<核心设定:") and source_body.rstrip().endswith(">"),"GREEN tag "+g["id"])
        b=g["build"]
        keys=list(dict.fromkeys(b["keys"]))
        assert_(keys,f"No GREEN keywords: {g['id']}")
        core_content.append((g["comment"],source_body,keys,bool(b.get("use_regex",False))))
    for i,name,cb,ab in members:
        core_content.append((f"核心设定:{name}·能力",ab,scene_by_id[i],True))
    assert_(len(core_content)==195,"Expected 67 GREENS + 128 ABILITY")
    for idx,(name,content,keys,use_regex) in enumerate(core_content):
        order=391-(idx*90//195)
        data.append(entry(name,content,order,keys,recursive=True,use_regex=use_regex))
    data.append(marker("核心设定","结尾",301))
    data.append(marker("主要角色","起始",300))
    major=set(range(1,38))|set(range(40,90))|{121,122,123,124}
    main=[x for x in members if x[0] in major]
    minor=[x for x in members if x[0] not in major]
    assert_(len(main)<=98 and len(minor)<=98,"Character subsection capacity")
    for idx,(i,name,cb,_) in enumerate(main):
        data.append(entry("角色:"+name,cb,299-idx,scene_by_id[i],recursive=True))
    data.append(marker("主要角色","结尾",201))
    data.append(marker("其他角色","起始",200))
    for idx,(i,name,cb,_) in enumerate(minor):
        data.append(entry("角色:"+name,cb,199-idx,scene_by_id[i],recursive=True))
    data.append(marker("其他角色","结尾",101))
    data.append(marker("地点","起始",100))
    locations=[]
    for mp in LOC_MANIFESTS:locations+=manifest(mp)
    assert_(len(LOC_MANIFESTS)==4 and len(locations)==27,"Expected 27 LOC across 4 manifests")
    assert_(len(set(e["id"] for e in locations))==27,"Duplicate LOC")
    locations.sort(key=lambda x:int(x["id"].split("-")[1]))
    assert_({int(x["id"][4:]) for x in locations}==set(range(1,29))-{17},"LOC-17 held")
    place_reg={}
    for idx,loc in enumerate(locations):
        body=source(loc["file"])
        assert_(body.startswith("<地点:") and "</地点:" in body and "介绍:" in body,"Location form "+loc["id"])
        keys=[position_regex(loc["aliases"],exclude=loc["id"]=="LOC-06")]
        place_reg[loc["id"]]=rx(keys[0])
        data.append(entry(loc["comment"],body,99-idx,keys,recursive=True))
    data.append(marker("地点","结尾",1))

    # Stable insertion-order within every block; never sort by comment or file name.
    assert_(all(data[i]["insertion_order"]>=data[i+1]["insertion_order"] for i in range(len(data)-1)),
            "Main array order must be descending")
    assert_(len(data)==409,f"Expected 409 entries, got {len(data)}")
    assert_(sum(x["enabled"] and x["comment"].startswith("时间线-") for x in data)==1,
            "Must only enable TL-01")
    assert_(all(x["enabled"] and x["constant"] for x in data if x["comment"].startswith("【")),
            "Dividers must be enabled")
    trigger=[x for x in data if not x["constant"]]
    assert_(len(trigger)==67+128+128+27,"Trigger count mismatch")
    assert_(all(x["keys"] and x["extensions"]["prevent_recursion"] and
         x["extensions"]["exclude_recursion"] for x in trigger),"Trigger safety")
    for i in range(128):
        a=data[[j for j,e in enumerate(data) if e["comment"]=="角色:"+members[i][1]][0]]
        b=data[[j for j,e in enumerate(data) if e["comment"]=="核心设定:"+members[i][1]+"·能力"][0]]
        assert_(a["keys"]==b["keys"],f"CHAR/ABILITY keywords differ {members[i][1]}")
    def status(s):return "<status>\n📅沙盒日期：1600年03月01日\n📍当前位置："+s+"\n❤️身体状况：健康\n</status>"
    collisions=[]
    for i,e in enumerate(locations):
        loc=e["id"]
        assert_(bool(place_reg[loc].search(status(e["aliases"][0]))),"Location fails with emoji "+loc)
        assert_(not place_reg[loc].search("<status>\n📍当前位置：无名荒原\n其他地点："+e["aliases"][0]+"\n</status>"),"Wrong status line "+loc)
        for other in locations:
            if other["id"]!=loc and place_reg[loc].search(status(other["aliases"][0])):
                collisions.append([loc,other["id"]])
    assert_(not collisions,f"Location collisions: {collisions}")
    # Entity settings shall never be infused into role metadata as secondary keywords.
    for i,e in enumerate(data):
        e["id"]=i
        e["extensions"]["display_index"]=i
        assert_(not (e["constant"] and e["keys"]),f"Constant/keys collision {i}")
        if e["position"]=="at_depth":
            assert_(e["extensions"]["position"]==4 and e["extensions"]["depth"]==0,"Depth zero failed")
    assert_(all(x["enabled"]==False for x in data if x["comment"] in
           ["日常记忆存储","重大记忆存储","玩家身世背景"]),"Memory must be off")
    assert_(all(not x["content"].startswith("<!--") for x in data if x["comment"].startswith("时间线-")),
            "Timeline must not contain engineering header")
    book={"name":"黑色四叶草·咩咩全栈世界书（27卷）",
      "entries":data,"extensions":{}}
    q={
      "build":VERSION,"status":"STATIC_QA_PASS_NOT_SILLYTAVERN_TESTED_NOT_FROZEN",
      "totals":{"entries":len(data),"markers":14,"reset":1,"memory_disabled":3,
          "blue":8,"green":67,"ability_green":128,"character":128,"timeline":27,
          "location":27,"fullstack_components":6},
      "invariant":{"one_timeline_only":True,"memory_slots_off":True,
         "recursive_trigger_safety":True,"per_character_same_keys":True,
         "section_order_descending":True,"display_index_matches_array":True,
         "no_mvu":True,"location_emoji_test":True,
         "location_wrong_field_test":True,"cross_place_pairs":27*26,"cross_place_collisions":0},
      "source_hold":["LOC-17钻石王国军政核心区域"],
      "known_warning":["TL-01 v4正文奇典镇黑市/奇卡镇用词待授权单点修订",
          "人物与能力的完整成长档案需要在实际对话中按TL事件锁定后期知识；静态正则不等于时间门控",
          "核心设定195条触发设定共享整数段位302～391，需酒馆实际验证同order排序",
          "Character Card V3内嵌世界书、开场、用户预设、移动端状态栏渲染尚未实机验收"]}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"黑色四叶草_character_book.json").write_text(json.dumps(book,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    (OUT/"黑色四叶草_装配静态QA.json").write_text(json.dumps(q,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({"result":"PASS",**q["totals"],"location_collisions":0},ensure_ascii=False))
if __name__=="__main__":build()
