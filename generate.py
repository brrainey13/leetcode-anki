# generate.py

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Awaitable, List
import html

import genanki  # type: ignore
from tqdm import tqdm  # type: ignore

import leetcode_anki.helpers.leetcode

LEETCODE_ANKI_MODEL_ID = 4567610856
LEETCODE_ANKI_DECK_ID = 8589798175
OUTPUT_FILE = "leetcode.apkg"


logging.getLogger().setLevel(logging.INFO)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments for the script
    """
    parser = argparse.ArgumentParser(description="Generate Anki cards for leetcode")
    parser.add_argument("--start", type=int, default=0)
    parser.add_argument("--stop", type=int, default=2**64)
    parser.add_argument("--page-size", type=int, default=500)
    parser.add_argument("--list-id", type=str, default="")
    parser.add_argument("--output-file", type=str, default=OUTPUT_FILE)
    # set the default to 'AC' so we only retrieve problems you've actually solved
    parser.add_argument(
        "--problem-status",
        type=str,
        default="AC",
        help="Set to 'AC' to only include problems you have accepted solutions for."
    )
    parser.add_argument(
        "--include-last-submission",
        type=bool,
        default=True,
        help="Fetch your last accepted submission. (heavy operation)"
    )

    args = parser.parse_args()
    return args


class LeetcodeNote(genanki.Note):
    @property
    def guid(self) -> str:
        return genanki.guid_for(self.fields[0])


async def generate_anki_note(
    leetcode_data: leetcode_anki.helpers.leetcode.LeetcodeData,
    leetcode_model: genanki.Model,
    leetcode_task_handle: str,
) -> LeetcodeNote:
    """
    Generate a single Anki flashcard
    """
    last_code = await leetcode_data.last_submission_code(leetcode_task_handle)
    # skip if there's no accepted code at all
    if not last_code or "No code found" in last_code:
        return None

    return LeetcodeNote(
        model=leetcode_model,
        fields=[
            leetcode_task_handle,
            str(await leetcode_data.problem_id(leetcode_task_handle)),
            str(await leetcode_data.title(leetcode_task_handle)),
            str(await leetcode_data.category(leetcode_task_handle)),
            await leetcode_data.description(leetcode_task_handle),
            await leetcode_data.difficulty(leetcode_task_handle),
            "yes" if await leetcode_data.paid(leetcode_task_handle) else "no",
            str(await leetcode_data.likes(leetcode_task_handle)),
            str(await leetcode_data.dislikes(leetcode_task_handle)),
            str(await leetcode_data.submissions_total(leetcode_task_handle)),
            str(await leetcode_data.submissions_accepted(leetcode_task_handle)),
            str(
                int(
                    await leetcode_data.submissions_accepted(leetcode_task_handle)
                    / await leetcode_data.submissions_total(leetcode_task_handle)
                    * 100
                )
            ),
            str(await leetcode_data.freq_bar(leetcode_task_handle)),
            "\n" + html.escape(last_code),
        ],
        tags=await leetcode_data.tags(leetcode_task_handle),
        sort_field=str(await leetcode_data.freq_bar(leetcode_task_handle)).zfill(3),
    )


async def generate(
    start: int,
    stop: int,
    page_size: int,
    list_id: str,
    output_file: str,
    problem_status: str,
    include_last_submission: bool,
) -> None:
    """
    Generate an Anki deck
    """
    leetcode_model = genanki.Model(
        LEETCODE_ANKI_MODEL_ID,
        "Leetcode model",
        fields=[
            {"name": "Slug"},
            {"name": "Id"},
            {"name": "Title"},
            {"name": "Topic"},
            {"name": "Content"},
            {"name": "Difficulty"},
            {"name": "Paid"},
            {"name": "Likes"},
            {"name": "Dislikes"},
            {"name": "SubmissionsTotal"},
            {"name": "SubmissionsAccepted"},
            {"name": "SumissionAcceptRate"},
            {"name": "Frequency"},
            {"name": "LastSubmissionCode"},
        ],
        templates=[
            {
                "name": "Leetcode",
                "qfmt": """
                <h2>{{Id}}. {{Title}}</h2>
                <b>Difficulty:</b> {{Difficulty}}<br/>
                &#128077; {{Likes}} &#128078; {{Dislikes}}<br/>
                <b>Submissions (total/accepted):</b>
                {{SubmissionsTotal}}/{{SubmissionsAccepted}}
                ({{SumissionAcceptRate}}%)
                <br/>
                <b>Topic:</b> {{Topic}}<br/>
                <b>Frequency:</b>
                <progress value="{{Frequency}}" max="100">
                {{Frequency}}%
                </progress>
                <br/>
                <b>URL:</b>
                <a href='https://leetcode.com/problems/{{Slug}}/'>
                    https://leetcode.com/problems/{{Slug}}/
                </a>
                <br/>
                <h3>Description</h3>
                {{Content}}
                """,
                "afmt": """
                {{FrontSide}}
                <hr id="answer">
                <b>Discuss URL:</b>
                <a href='https://leetcode.com/problems/{{Slug}}/discuss/'>
                    https://leetcode.com/problems/{{Slug}}/discuss/
                </a>
                <br/>
                <b>Solution URL:</b>
                <a href='https://leetcode.com/problems/{{Slug}}/solution/'>
                    https://leetcode.com/problems/{{Slug}}/solution/
                </a>
                {{#LastSubmissionCode}}
                    <br/>
                    <b>Accepted Last Submission:</b>
                    <pre>
                    <code>
                    {{LastSubmissionCode}}
                    </code>
                    </pre>
                    <br/>
                {{/LastSubmissionCode}}
                """,
            }
        ],
    )
    leetcode_deck = genanki.Deck(LEETCODE_ANKI_DECK_ID, Path(output_file).stem)

    leetcode_data = leetcode_anki.helpers.leetcode.LeetcodeData(
        start,
        stop,
        page_size,
        list_id,
        problem_status,
        include_last_submission,
    )

    note_generators: List[Awaitable[LeetcodeNote]] = []
    task_handles = await leetcode_data.all_problems_handles()

    logging.info("Generating flashcards (only for AC submissions).")
    for handle in tqdm(task_handles, unit="flashcard"):
        note_generators.append(
            generate_anki_note(leetcode_data, leetcode_model, handle)
        )

    for note_coro in note_generators:
        note = await note_coro
        if note is not None:
            leetcode_deck.add_note(note)

    genanki.Package(leetcode_deck).write_to_file(output_file)


async def main() -> None:
    args = parse_args()
    await generate(
        args.start,
        args.stop,
        args.page_size,
        args.list_id,
        args.output_file,
        args.problem_status,
        args.include_last_submission,
    )


if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())