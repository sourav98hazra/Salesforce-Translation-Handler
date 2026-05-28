import pandas as pd
import time
import re
import argparse
from deep_translator import GoogleTranslator
from bs4 import BeautifulSoup, NavigableString


# --- Helper: Protect placeholders and CAPS words ---
def protect_tokens(text):
    """
    Protects Salesforce placeholders (e.g., {!$Label.Name}, {!Record.Id})
    and ALL CAPS words (e.g., WO, API) with unique tokens.
    """
    token_map = []
    counter = 0

    # Step 1: Protect placeholders (with spacing preserved)
    def repl_placeholder(match):
        nonlocal counter
        token = f"__PLACEHOLDER_{counter}__"
        token_map.append((token, match.group(0)))
        counter += 1
        return token

    safe_text = re.sub(r"(\s*\{![^}]+\}\s*)", repl_placeholder, text)

    # Step 2: Protect CAPS words (≥2 chars)
    def repl_caps(match):
        nonlocal counter
        token = f"__CAPS_{counter}__"
        token_map.append((token, match.group(0)))
        counter += 1
        return token

    safe_text = re.sub(r"\b([A-Z]{2,})\b", repl_caps, safe_text)

    return safe_text, token_map


def restore_tokens(text, token_map):
    """
    Restores tokens back into the translated string,
    tolerant of case and extra spaces inside tokens.
    """
    restored = text
    for token, ph in token_map:
        # Build regex pattern that allows arbitrary whitespace inside token
        token_regex = "".join(
            f"{re.escape(ch)}\\s*" if ch == "_" else f"{re.escape(ch)}\\s*"
            for ch in token
        )
        token_pattern = re.compile(token_regex, re.IGNORECASE)
        restored = token_pattern.sub(ph, restored, count=1)
    return restored


# --- Core translation function ---
def translate_preserve_html(text, source_lang, target_lang, retries=3, delay=1):
    if not text or str(text).strip().lower() in ["nan", "none"]:
        return text

    soup = BeautifulSoup(f"<span>{text}</span>", "html.parser")

    for elem in soup.descendants:
        if isinstance(elem, NavigableString) and elem.strip():
            original = str(elem)

            # Protect placeholders + CAPS words
            safe_text, token_map = protect_tokens(original)

            translated = None
            for attempt in range(retries):
                try:
                    translated = GoogleTranslator(
                        source=source_lang, target=target_lang
                    ).translate(safe_text)
                    if translated and translated.strip():
                        break
                except Exception:
                    pass
                time.sleep(delay * (2**attempt))  # exponential backoff

            # Fallback: keep original if no translation
            if not translated or translated.strip() == "":
                elem.replace_with(original)
                continue

            # Restore tokens (placeholders + CAPS)
            translated = restore_tokens(translated, token_map)

            # Safeguard: if translation == original ignoring case → keep original
            if translated.strip().lower() == original.strip().lower():
                translated = original

            elem.replace_with(translated or "")

    return "".join(str(x) for x in soup.span.contents)


# --- Runner function ---
def run_translation(input_path, output_path, source_lang, target_lang):
    print(f"🔍 Reading Excel: {input_path}")
    sheets = pd.read_excel(input_path, sheet_name=None)
    translated_sheets = {}
    summary_data = []
    status_log = []

    total_rows = sum(
        len(df)
        for df in sheets.values()
        if {"Key", "Label", "Translation"}.issubset(df.columns)
    )
    completed = 0

    for sheet_name, df in sheets.items():
        print(f"\n📄 Processing sheet: {sheet_name}")

        if {"Key", "Label", "Translation"}.issubset(df.columns):
            df["Translation"] = df["Translation"].astype(str)
            total_rows_sheet = len(df)
            translated_rows = 0

            for idx, row in df.iterrows():
                key = str(row["Key"])
                label = str(row["Label"])
                translation = str(row["Translation"])

                status_entry = {
                    "Sheet Name": sheet_name,
                    "Row Index": idx + 2,
                    "Key": key,
                    "Label": label,
                }

                if (
                    pd.notna(label)
                    and label.strip().lower() not in ["", "nan"]
                    and translation.strip().lower() in ["", "nan"]
                ):
                    try:
                        translated = translate_preserve_html(
                            label, source_lang, target_lang
                        )
                        df.at[idx, "Translation"] = translated
                        translated_rows += 1
                        status_entry["Status"] = "✅ Translated"

                        print(f"✅ [{translated_rows}/{total_rows_sheet}] {key}")
                        print(f"    {source_lang.upper()} : {label}")
                        print(f"    {target_lang.upper()} : {translated}")

                    except Exception as e:
                        df.at[idx, "Translation"] = label  # keep original if failed
                        status_entry["Status"] = f"⚠️ Fallback to original ({e})"
                        print(f"⚠️ [{translated_rows}/{total_rows_sheet}] {key} → Fallback: {e}")
                else:
                    status_entry["Status"] = "⏭️ Skipped"
                    print(f"⏭️ [{idx+1}/{total_rows_sheet}] Skipped {key} (already translated or blank)")

                status_log.append(status_entry)
                completed += 1
                percent = int((completed / total_rows) * 100)
                print(f"Progress: {percent}%")

            skipped_rows = total_rows_sheet - translated_rows
            summary_data.append(
                {
                    "Sheet Name": sheet_name,
                    "Total Rows": total_rows_sheet,
                    "Translated Rows": translated_rows,
                    "Skipped Rows": skipped_rows,
                }
            )
        else:
            print(f"⚠️ Sheet '{sheet_name}' skipped (missing required columns)")

        translated_sheets[sheet_name] = df

    # Add summary and status log
    translated_sheets["Translation_Summary"] = pd.DataFrame(summary_data)
    translated_sheets["Translation_Status_Log"] = pd.DataFrame(status_log)

    print(f"\n💾 Saving translated Excel to: {output_path}")

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        for name, df in translated_sheets.items():
            df.to_excel(writer, sheet_name=name[:31], index=False)

    print("🎉 Translation completed!")


# --- CLI entry point ---
if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Translate Salesforce STF Excel with placeholders and CAPS preserved."
    )
    parser.add_argument("input", help="Path to input Excel file")
    parser.add_argument("output", help="Path to save translated Excel file")
    parser.add_argument("--source", default="en", help="Source language (default: en)")
    parser.add_argument("--target", default="ja", help="Target language (default: ja)")
    args = parser.parse_args()

    run_translation(args.input, args.output, args.source, args.target)
