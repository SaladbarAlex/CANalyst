"""Add entrance builds to slides from shape names written by the deck builder.

A shape named "anim:<order>:<kind>:..." enters in group <order> when the slide starts.
Kinds: drop, rise, grow, fade, wipe, count. Count shapes in one group appear one after
another, which ticks a stacked number upward. Charts wipe up and tables rise in group 1.
Builds start automatically, so the presenter's clicks still only advance slides.
"""

import argparse
import re
from collections import defaultdict
from pathlib import Path
from zipfile import ZipFile

from lxml import etree as xml

P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
NS = {"p": P, "a": A}
GROUP_GAP_MS = 280
COUNT_STEP_MS = 120


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    if args.source.resolve() == args.output.resolve():
        parser.error("output must be separate from the source")
    animated = 0
    with ZipFile(args.source) as source, ZipFile(args.output, "w") as output:
        for entry in source.infolist():
            content = source.read(entry.filename)
            if re.fullmatch(r"ppt/slides/slide\d+\.xml", entry.filename):
                content, changed = animate(content)
                animated += changed
            output.writestr(entry, content)
    print(f"Added entrance builds to {animated} slides in {args.output}")


def animate(content):
    slide = xml.fromstring(content)
    if slide.find("p:timing", NS) is not None:
        return content, 0
    groups = collect(slide)
    if not groups:
        return content, 0
    ids = iter(range(3, 100_000))
    first, second = next(ids), next(ids)
    effects = []
    builds = []
    for position, order in enumerate(sorted(groups)):
        start = 150 + position * GROUP_GAP_MS
        counted = 0
        for spid, kind in groups[order]:
            delay = start + counted * COUNT_STEP_MS if kind == "count" else start
            counted += kind == "count"
            effects.append(effect(ids, spid, kind, delay))
            builds.append(BUILD_GRAPHIC.format(spid=spid) if kind in ("chart", "table") else BUILD_SHAPE.format(spid=spid))
    timing = xml.fromstring(TIMING.format(effects="".join(effects), first=first, second=second, builds="".join(builds)))
    anchor = slide.find("p:clrMapOvr", NS)
    (anchor if anchor is not None else slide.find("p:cSld", NS)).addnext(timing)
    return xml.tostring(slide, encoding="UTF-8", xml_declaration=True, standalone=True), 1


def collect(slide):
    groups = defaultdict(list)
    for properties in slide.iterfind(".//p:cSld/p:spTree//p:cNvPr", NS):
        name = properties.get("name", "")
        match = re.match(r"anim:(\d+):(\w+):", name)
        if match:
            groups[int(match[1])].append((properties.get("id"), match[2]))
            continue
        frame = properties.getparent().getparent()
        if frame.tag != f"{{{P}}}graphicFrame":
            continue
        uri = frame.find(".//a:graphicData", NS).get("uri", "")
        groups[0].append((properties.get("id"), "chart" if "chart" in uri else "table"))
    return groups


def effect(ids, spid, kind, delay):
    node = next(ids)
    visible = SET.format(id=next(ids), spid=spid)
    fade = lambda dur: FADE.format(id=next(ids), dur=dur, spid=spid)
    wipe = lambda dur, direction: WIPE.format(id=next(ids), dur=dur, spid=spid, direction=direction)
    move = lambda attr, start, end: MOVE.format(id=next(ids), spid=spid, attr=attr, start=start, end=end)
    if kind == "drop":
        body = fade(350) + move("ppt_y", "#ppt_y-0.045", "#ppt_y")
    elif kind in ("rise", "table"):
        body = fade(350) + move("ppt_y", "#ppt_y+0.045", "#ppt_y")
    elif kind == "grow":
        body = fade(300) + move("ppt_w", "#ppt_w*0.6", "#ppt_w") + move("ppt_h", "#ppt_h*0.6", "#ppt_h")
    elif kind == "fade":
        body = fade(450)
    elif kind == "wipe":
        body = wipe(700, "left")
    elif kind == "chart":
        body = wipe(800, "down")
    else:
        body = ""
    preset = {"drop": (42, 0), "rise": (42, 0), "table": (42, 0), "grow": (53, 16), "fade": (10, 0), "wipe": (22, 8), "chart": (22, 4), "count": (1, 0)}[kind]
    return EFFECT.format(id=node, delay=delay, preset=preset[0], subtype=preset[1], body=visible + body)


SET = ('<p:set><p:cBhvr><p:cTn id="{id}" dur="1" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst></p:cTn>'
       '<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl><p:attrNameLst><p:attrName>style.visibility</p:attrName></p:attrNameLst>'
       '</p:cBhvr><p:to><p:strVal val="visible"/></p:to></p:set>')
FADE = ('<p:animEffect transition="in" filter="fade"><p:cBhvr><p:cTn id="{id}" dur="{dur}"/>'
        '<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>')
WIPE = ('<p:animEffect transition="in" filter="wipe({direction})"><p:cBhvr><p:cTn id="{id}" dur="{dur}"/>'
        '<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl></p:cBhvr></p:animEffect>')
BUILD_SHAPE = '<p:bldP spid="{spid}" grpId="0" animBg="1"/>'
BUILD_GRAPHIC = '<p:bldGraphic spid="{spid}" grpId="0"><p:bldAsOne/></p:bldGraphic>'
MOVE = ('<p:anim calcmode="lin" valueType="num"><p:cBhvr additive="base"><p:cTn id="{id}" dur="550" decel="100000" fill="hold"/>'
        '<p:tgtEl><p:spTgt spid="{spid}"/></p:tgtEl><p:attrNameLst><p:attrName>{attr}</p:attrName></p:attrNameLst></p:cBhvr>'
        '<p:tavLst><p:tav tm="0"><p:val><p:strVal val="{start}"/></p:val></p:tav>'
        '<p:tav tm="100000"><p:val><p:strVal val="{end}"/></p:val></p:tav></p:tavLst></p:anim>')
EFFECT = ('<p:par><p:cTn id="{id}" presetID="{preset}" presetClass="entr" presetSubtype="{subtype}" fill="hold" grpId="0" nodeType="withEffect">'
          '<p:stCondLst><p:cond delay="{delay}"/></p:stCondLst><p:childTnLst>{body}</p:childTnLst></p:cTn></p:par>')
TIMING = (f'<p:timing xmlns:p="{P}"><p:tnLst><p:par><p:cTn id="1" dur="indefinite" restart="never" nodeType="tmRoot"><p:childTnLst>'
          '<p:seq concurrent="1" nextAc="seek"><p:cTn id="2" dur="indefinite" nodeType="mainSeq"><p:childTnLst>'
          '<p:par><p:cTn id="{first}" fill="hold"><p:stCondLst><p:cond delay="indefinite"/><p:cond evt="onBegin" delay="0"><p:tn val="2"/></p:cond></p:stCondLst>'
          '<p:childTnLst><p:par><p:cTn id="{second}" fill="hold"><p:stCondLst><p:cond delay="0"/></p:stCondLst>'
          '<p:childTnLst>{effects}</p:childTnLst></p:cTn></p:par></p:childTnLst></p:cTn></p:par>'
          '</p:childTnLst></p:cTn><p:prevCondLst><p:cond evt="onPrev" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:prevCondLst>'
          '<p:nextCondLst><p:cond evt="onNext" delay="0"><p:tgtEl><p:sldTgt/></p:tgtEl></p:cond></p:nextCondLst></p:seq>'
          '</p:childTnLst></p:cTn></p:par></p:tnLst><p:bldLst>{builds}</p:bldLst></p:timing>')


if __name__ == "__main__":
    main()
