"""Add the CANalyst experiment MP4 to a PowerPoint slide using the template's playback timing."""

import argparse
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from posixpath import dirname, join, normpath, relpath
from tempfile import NamedTemporaryFile
from zipfile import ZIP_STORED, ZipFile

from lxml import etree as xml


P = "http://schemas.openxmlformats.org/presentationml/2006/main"
A = "http://schemas.openxmlformats.org/drawingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P14 = "http://schemas.microsoft.com/office/powerpoint/2010/main"
REL = "http://schemas.openxmlformats.org/package/2006/relationships"
CT = "http://schemas.openxmlformats.org/package/2006/content-types"
MEDIA_REL = "http://schemas.microsoft.com/office/2007/relationships/media"
NS = {"p": P, "a": A, "r": R, "p14": P14}
VIDEO_PART = "ppt/media/canalyst-experiment-flow.mp4"
CONTENT_TYPES = "[Content_Types].xml"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("candidate", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("template", type=Path)
    parser.add_argument("video", type=Path)
    parser.add_argument("slide_number", type=int, nargs="?", default=4)
    parser.add_argument("--duration-ms", type=int, default=42_000)
    args = parser.parse_args()
    if min(args.duration_ms, args.slide_number) <= 0:
        parser.error("slide number and duration must be positive")
    if args.output.resolve() in {path.resolve() for path in (args.candidate, args.template, args.video)}:
        parser.error("output must be separate from the candidate, template and video")

    video = args.video.read_bytes()
    if video[4:8] != b"ftyp":
        parser.error("video must be an MP4 file")

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=args.output.parent, prefix=".video-deck-", delete=False) as temp:
        draft = Path(temp.name)
    try:
        with ZipFile(args.candidate) as candidate, ZipFile(args.template) as template:
            slide = slide_part(candidate, args.slide_number)
            updates = embed(candidate, template, slide, args.duration_ms)
            with ZipFile(draft, "w") as output:
                for entry in candidate.infolist():
                    content = updates[entry.filename] if entry.filename in updates else candidate.read(entry)
                    output.writestr(entry, content)
                output.writestr(VIDEO_PART, video, compress_type=ZIP_STORED)
        verify(draft, slide, sha256(video).digest(), args.duration_ms)
        draft.replace(args.output)
    finally:
        draft.unlink(missing_ok=True)
    print(f"Embedded and verified {args.duration_ms} ms of video on slide {args.slide_number} in {args.output}")


def embed(candidate, template, slide_part_name, duration):
    slide = read_xml(candidate, slide_part_name)
    relationships_part = rels_part(slide_part_name)
    relationships = read_xml(candidate, relationships_part)
    content_types = read_xml(candidate, CONTENT_TYPES)
    if VIDEO_PART in candidate.namelist() or slide.find("p:timing", NS) is not None:
        raise ValueError("candidate already contains video media or slide timing")

    poster = only(slide.findall(".//p:pic", NS), "poster on candidate slide")
    poster_properties = poster.find("p:nvPicPr/p:cNvPr", NS)
    shape_id = poster_properties.get("id")
    donor = read_xml(template, slide_part(template, 7))
    picture = deepcopy(only(donor.findall(".//p:pic", NS), "video on template slide 7"))
    timing = deepcopy(donor.find("p:timing", NS))
    properties = picture.find("p:nvPicPr/p:cNvPr", NS)
    previous_id = properties.get("id")
    properties.set("id", shape_id)
    properties.set("name", "CANalyst experiment animation")
    properties.set("descr", poster_properties.get("descr") or "Animated CANalyst experiment workflow")
    click = properties.find("a:hlinkClick", NS)
    if click is not None and click.get(f"{{{R}}}id") == "":
        del click.attrib[f"{{{R}}}id"]

    # Keep the authored poster and position. Use the template's playable picture properties.
    for path in ("p:blipFill", "p:spPr/a:xfrm"):
        target = picture.find(path, NS)
        target.getparent().replace(target, deepcopy(poster.find(path, NS)))
    poster.getparent().replace(poster, picture)

    internal_target = relpath(VIDEO_PART, dirname(slide_part_name))
    video_id = add_relationship(relationships, f"{R}/video", internal_target)
    media_id = add_relationship(relationships, MEDIA_REL, internal_target)
    picture.find(".//a:videoFile", NS).set(f"{{{R}}}link", video_id)
    picture.find(".//p14:media", NS).set(f"{{{R}}}embed", media_id)
    for target in timing.findall(".//p:spTgt", NS):
        if target.get("spid") != previous_id:
            raise ValueError("template timing refers to a shape other than the video")
        target.set("spid", shape_id)
    playback_duration(timing).set("dur", str(duration))
    extensions = slide.find("p:extLst", NS)
    slide.insert(slide.index(extensions) if extensions is not None else len(slide), timing)

    mp4 = content_types.find(f"{{{CT}}}Default[@Extension='mp4']")
    if mp4 is None:
        mp4 = xml.Element(f"{{{CT}}}Default", Extension="mp4", ContentType="video/mp4")
        content_types.insert(0, mp4)
    if mp4.get("ContentType") != "video/mp4":
        raise ValueError("candidate has an unexpected MP4 content type")
    return {
        part: xml.tostring(element, encoding="UTF-8", xml_declaration=True, standalone=True)
        for part, element in ((slide_part_name, slide), (relationships_part, relationships), (CONTENT_TYPES, content_types))
    }


def verify(path, slide_part_name, expected_hash, duration):
    with ZipFile(path) as deck:
        if deck.testzip() is not None or sha256(deck.read(VIDEO_PART)).digest() != expected_hash:
            raise ValueError("embedded MP4 or deck archive failed verification")
        slide = read_xml(deck, slide_part_name)
        relationships = read_xml(deck, rels_part(slide_part_name))
        picture = only(slide.findall(".//p:pic", NS), "embedded video picture")
        properties = picture.find("p:nvPicPr/p:cNvPr", NS)
        shape_id = properties.get("id")
        click = properties.find("a:hlinkClick", NS)
        if click is None or click.get("action") != "ppaction://media" or f"{{{R}}}id" in click.attrib:
            raise ValueError("video lacks a native media click action")
        for tag, attribute, kind in (
            ("a:videoFile", "link", f"{R}/video"),
            ("p14:media", "embed", MEDIA_REL),
            ("a:blip", "embed", f"{R}/image"),
        ):
            reference = picture.find(f".//{tag}", NS).get(f"{{{R}}}{attribute}")
            relationship = relationships.find(f"{{{REL}}}Relationship[@Id='{reference}']")
            if relationship is None or relationship.get("Type") != kind:
                raise ValueError(f"invalid relationship for {tag}")
            target = relationship_target(slide_part_name, relationship)
            if target not in deck.namelist() or (tag != "a:blip" and target != VIDEO_PART):
                raise ValueError(f"missing or incorrect relationship target for {tag}")
        timing = slide.find("p:timing", NS)
        targets = {node.get("spid") for node in timing.findall(".//p:spTgt", NS)}
        if targets != {shape_id} or playback_duration(timing).get("dur") != str(duration):
            raise ValueError("video timing failed verification")
        mp4 = read_xml(deck, CONTENT_TYPES).find(f"{{{CT}}}Default[@Extension='mp4']")
        if mp4 is None or mp4.get("ContentType") != "video/mp4":
            raise ValueError("missing MP4 content type")


def only(elements, description):
    if len(elements) != 1:
        raise ValueError(f"expected exactly one {description}, found {len(elements)}")
    return elements[0]


def read_xml(deck, part):
    return xml.fromstring(deck.read(part))


def slide_part(deck, number):
    presentation = "ppt/presentation.xml"
    slides = read_xml(deck, presentation).findall("p:sldIdLst/p:sldId", NS)
    if not 1 <= number <= len(slides):
        raise ValueError(f"slide {number} is outside the deck's slide range")
    reference = slides[number - 1].get(f"{{{R}}}id")
    relationships = read_xml(deck, rels_part(presentation))
    relationship = relationships.find(f"{{{REL}}}Relationship[@Id='{reference}']")
    return relationship_target(presentation, relationship)


def rels_part(part):
    parent, name = part.rsplit("/", 1)
    return f"{parent}/_rels/{name}.rels"


def relationship_target(source, relationship):
    if relationship.get("TargetMode") not in (None, "Internal"):
        raise ValueError("expected a relationship with an embedded target")
    target = relationship.get("Target")
    return target.lstrip("/") if target.startswith("/") else normpath(join(dirname(source), target))


def add_relationship(relationships, kind, target):
    occupied = {relationship.get("Id") for relationship in relationships}
    index = 1
    while f"rId{index}" in occupied:
        index += 1
    name = f"rId{index}"
    xml.SubElement(relationships, f"{{{REL}}}Relationship", Id=name, Type=kind, Target=target)
    return name


def playback_duration(timing):
    command = only(timing.findall(".//p:cmd[@cmd='playFrom(0.0)']", NS), "template playback command")
    return command.find("p:cBhvr/p:cTn", NS)


if __name__ == "__main__":
    main()
