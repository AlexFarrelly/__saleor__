# Generated by Django 3.1 on 2020-11-06 08:44

from collections import defaultdict

from django.db import migrations

LEVELS_MAPPING = {"one": 1, "two": 2, "three": 3}
TAG_MAPPING = {
    "BOLD": "b",
    "ITALIC": "i",
    "STRIKETHROUGH": "s",
    "CODE": "code",
}


def parse_to_editorjs(data):
    blocks = data.get("blocks")
    entity_map = data.get("entityMap")

    if not blocks:
        return data

    editor_js_blocks = []
    list_data = {}
    for block in blocks:
        # if block doesn't have key it means it isn't in draft.js format
        if "key" not in block:
            return data
        key = block["type"]
        inline_style_ranges = block["inlineStyleRanges"]
        entity_ranges = block["entityRanges"]

        text = block["text"]
        text = parse_text(text, inline_style_ranges, entity_ranges, entity_map)

        type, data = get_block_data(text, key, list_data, editor_js_blocks)

        if not type:
            continue

        new_block = {
            "type": type,
            "data": data,
        }
        editor_js_blocks.append(new_block)

    return {"blocks": editor_js_blocks}


def parse_text(text, style_ranges, entity_ranges, entity_map):
    operations = defaultdict(list)
    prepare_operations(operations, style_ranges, entity_map, False)
    prepare_operations(operations, entity_ranges, entity_map, True)

    parsed_text = ""
    previous_index = 0
    # insert html element on specified indexes
    for offset, tags in operations.items():
        end_index = offset + 1
        parsed_text += text[previous_index:end_index]
        parsed_text += "".join(tags)
        previous_index = offset + 1

    parsed_text += text[previous_index:]

    return parsed_text


def prepare_operations(operations, ranges, entity_map, entity):
    """Prepare operations dict defining operations on specific indexes.

    Data format:
        - key: index value
        - value: list of html elements that should be insert into text on specific index

    """
    for range_date in ranges:
        tag = "a" if entity else TAG_MAPPING[range_date["style"]]
        offset = range_date["offset"]
        length = offset + range_date["length"] - 1
        if entity:
            entity_key = str(range_date["key"])
            href = entity_map[entity_key]["data"]["url"]
            start_tag = f'{tag} href="{href}"'
        else:
            start_tag = tag if tag != "code" else tag + ' class="inline-code"'
        operations[offset - 1].append(f"<{start_tag}>")
        operations[length] = [f"</{tag}>"] + operations[length]


def get_block_data(text, key, list_data, editor_js_blocks):
    """Prepare editorjs blocks based on draftjs blocks.

    Draftjs types are replaces with corresponding editorjs types.

    List must be handled specially. In draftjs every list item is in separate block,
    but in editorjs all list items are in a list in one block.
    """
    # if the list_data is not empty and list elements ended, append list block
    if list_data and "list-item" not in key:
        list_block = {"type": "list", "data": list_data}
        editor_js_blocks.append(list_block)
        list_data = {}

    if "list-item" in key:
        style = key.split("-")[0]
        # if the list data is not empty and list style is the same as current block,
        # just append list element to the list data
        if list_data and list_data["style"] == style:
            list_data["items"].append(text)
        else:
            # if the list data is not empty it means that list style has been changed,
            # in this situation create new block from existing list data and
            # override the list data with the new data
            if list_data:
                list_block = {"type": "list", "data": list_data}
                editor_js_blocks.append(list_block)
            list_data = {"style": style, "items": [text]}
        return None, None

    data = {"text": text}
    if key.startswith("header"):
        level = LEVELS_MAPPING[key.split("-")[1]]
        type = "header"
        data["level"] = level
    elif key == "blockquote":
        type = "quote"
        data["alignment"] = "left"
    elif key == "code-block":
        type = "code"
    else:
        type = "paragraph"

    return type, data


def migrate_draftjs_to_editorjs_format(apps, schema_editor):
    Page = apps.get_model("page", "Page")
    PageTranslation = apps.get_model("page", "PageTranslation")

    for model in [Page, PageTranslation]:
        migrate_model_field_data(model)


def migrate_model_field_data(Model):
    queryset = Model.objects.all().order_by("pk")
    for batch_pks in queryset_in_batches(queryset):
        instances = []
        batch = Model.objects.filter(pk__in=batch_pks)
        for instance in batch:
            if instance.content_json:
                instance.content_json = parse_to_editorjs(instance.content_json)
                instances.append(instance)

        Model.objects.bulk_update(instances, ["content_json"])


def queryset_in_batches(queryset):
    """Slice a queryset into batches.

    Input queryset should be sorted be pk.
    """
    start_pk = 0

    while True:
        qs = queryset.order_by("pk").filter(pk__gt=start_pk)[:2000]
        pks = list(qs.values_list("pk", flat=True))

        if not pks:
            break

        yield pks

        start_pk = pks[-1]


class Migration(migrations.Migration):

    dependencies = [
        ("page", "0014_add_metadata"),
    ]

    operations = [
        migrations.RunPython(
            migrate_draftjs_to_editorjs_format, migrations.RunPython.noop
        )
    ]
