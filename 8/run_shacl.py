from pathlib import Path
from pyshacl import validate


def run_one(data_file, shapes_file, title, ont_file=None):
    conforms, results_graph, results_text = validate(
        data_graph=data_file,
        shacl_graph=shapes_file,
        ont_graph=ont_file,
        data_graph_format="turtle",
        shacl_graph_format="turtle",
        inference="rdfs",
        abort_on_first=False,
        meta_shacl=False,
        advanced=True,
        js=False,
        debug=False,
    )
    print(f"{title}: conforms={conforms}")
    print(results_text[:1500])
    print("---")
    return conforms, results_text


def main():
    shapes = "shapes.ttl"
    md = ["# Звіт SHACL-валідації (pyshacl)\n\n"]
    md.append("Форми: `shapes.ttl` (операція, ризик, рахунок).\n\n")

    for data, title, ont in [
        ("data.ttl", "Основний набір даних (`data.ttl` + `vocabulary.ttl`)", "vocabulary.ttl"),
        ("valid_example.ttl", "Валідний приклад (`valid_example.ttl`)", None),
        ("invalid_example.ttl", "Невалідний приклад (`invalid_example.ttl`)", None),
    ]:
        conforms, text = run_one(data, shapes, title, ont)
        md.append(f"## {title}\n\n")
        md.append(f"**conforms:** `{conforms}`\n\n")
        md.append("```\n")
        md.append(text.strip() + "\n")
        md.append("```\n\n")

    Path("shacl_report.md").write_text("".join(md), encoding="utf-8")
    print("Збережено shacl_report.md")


if __name__ == "__main__":
    main()
