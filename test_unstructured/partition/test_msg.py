"""Test suite for `unstructured.partition.msg` module."""

from __future__ import annotations

import pathlib

import msg_parser
import pytest
from pytest_mock import MockFixture

from test_unstructured.unit_utils import (
    LogCaptureFixture,
    MonkeyPatch,
    assert_round_trips_through_JSON,
    example_doc_path,
)
from unstructured.chunking.title import chunk_by_title
from unstructured.documents.elements import (
    ElementMetadata,
    ListItem,
    NarrativeText,
    Title,
)
from unstructured.partition.msg import extract_msg_attachment_info, partition_msg
from unstructured.partition.text import partition_text
from unstructured.partition.utils.constants import UNSTRUCTURED_INCLUDE_DEBUG_METADATA

EXPECTED_MSG_OUTPUT = [
    NarrativeText(text="This is a test email to use for unit tests."),
    Title(text="Important points:"),
    ListItem(text="Roses are red"),
    ListItem(text="Violets are blue"),
]

ATTACH_EXPECTED_OUTPUT = [
    {
        "filename": "fake-attachment.txt",
        "extension": ".txt",
        "file_size": "unknown",
        "payload": b"Hey this is a fake attachment!",
    },
]


def test_partition_msg_from_filename():
    filename = example_doc_path("fake-email.msg")
    elements = partition_msg(filename=filename)
    parent_id = elements[0].metadata.parent_id

    assert elements == EXPECTED_MSG_OUTPUT
    assert (
        elements[0].metadata.to_dict()
        == ElementMetadata(
            coordinates=None,
            filename=filename,
            last_modified="2022-12-16T17:04:16-05:00",
            page_number=None,
            url=None,
            sent_from=["Matthew Robinson <mrobinson@unstructured.io>"],
            sent_to=["Matthew Robinson (None)"],
            subject="Test Email",
            filetype="application/vnd.ms-outlook",
            parent_id=parent_id,
            languages=["eng"],
        ).to_dict()
    )
    for element in elements:
        assert element.metadata.filename == "fake-email.msg"
    if UNSTRUCTURED_INCLUDE_DEBUG_METADATA:
        assert {element.metadata.detection_origin for element in elements} == {"msg"}


def test_partition_msg_from_filename_returns_uns_elements():
    filename = example_doc_path("fake-email.msg")
    elements = partition_msg(filename=filename)
    assert isinstance(elements[0], NarrativeText)


def test_partition_msg_from_filename_with_metadata_filename():
    filename = example_doc_path("fake-email.msg")
    elements = partition_msg(filename=filename, metadata_filename="test")
    assert all(element.metadata.filename == "test" for element in elements)


class MockMsOxMessage:
    def __init__(self, filename: str):
        self.body = "Here is an email with plain text."
        self.header_dict = {"Content-Type": "text/plain"}


def test_partition_msg_from_filename_with_text_content(monkeypatch: MonkeyPatch):
    monkeypatch.setattr(msg_parser, "MsOxMessage", MockMsOxMessage)
    filename = example_doc_path("fake-email.msg")
    elements = partition_msg(filename=filename)
    assert str(elements[0]) == "Here is an email with plain text."
    assert elements[0].metadata.filename == "fake-email.msg"
    assert elements[0].metadata.file_directory == example_doc_path("")


def test_partition_msg_raises_with_missing_file():
    filename = example_doc_path("doesnt-exist.msg")
    with pytest.raises(FileNotFoundError):
        partition_msg(filename=filename)


def test_partition_msg_from_file():
    filename = example_doc_path("fake-email.msg")
    with open(filename, "rb") as f:
        elements = partition_msg(file=f)
    assert elements == EXPECTED_MSG_OUTPUT
    for element in elements:
        assert element.metadata.filename is None


def test_partition_msg_from_file_with_metadata_filename():
    filename = example_doc_path("fake-email.msg")
    with open(filename, "rb") as f:
        elements = partition_msg(file=f, metadata_filename="test")
    assert elements == EXPECTED_MSG_OUTPUT
    for element in elements:
        assert element.metadata.filename == "test"


def test_extract_attachment_info():
    filename = example_doc_path("fake-email-attachment.msg")
    attachment_info = extract_msg_attachment_info(filename)
    assert len(attachment_info) > 0
    assert attachment_info == ATTACH_EXPECTED_OUTPUT


def test_partition_msg_raises_with_both_specified():
    filename = example_doc_path("fake-email.msg")
    with open(filename, "rb") as f, pytest.raises(ValueError):
        partition_msg(filename=filename, file=f)


def test_partition_msg_raises_with_neither():
    with pytest.raises(ValueError):
        partition_msg()


def test_partition_msg_from_filename_exclude_metadata():
    filename = example_doc_path("fake-email.msg")
    elements = partition_msg(filename=filename, include_metadata=False)

    for i in range(len(elements)):
        assert elements[i].metadata.to_dict() == {}


def test_partition_msg_from_file_exclude_metadata():
    filename = example_doc_path("fake-email.msg")
    with open(filename, "rb") as f:
        elements = partition_msg(file=f, include_metadata=False)

    for i in range(len(elements)):
        assert elements[i].metadata.to_dict() == {}


def test_partition_msg_can_process_attachments(tmp_path: pathlib.Path):
    file_path = example_doc_path("fake-email-attachment.msg")
    tmp_dir_path = str(tmp_path)
    extract_msg_attachment_info(filename=file_path, output_dir=tmp_dir_path)
    attachment_filename = str(tmp_path / str(ATTACH_EXPECTED_OUTPUT[0]["filename"]))

    mocked_last_modification_date = "2029-07-05T09:24:28"

    attachment_elements = partition_text(
        filename=attachment_filename,
        metadata_filename=attachment_filename,
        metadata_last_modified=mocked_last_modification_date,
    )
    expected_metadata = attachment_elements[0].metadata
    expected_metadata.file_directory = None
    expected_metadata.attached_to_filename = file_path

    elements = partition_msg(
        filename=file_path,
        attachment_partitioner=partition_text,
        process_attachments=True,
        metadata_last_modified=mocked_last_modification_date,
    )

    # This test does not need to validate if hierarchy is working
    # Patch to nullify parent_id
    expected_metadata.parent_id = None
    elements[-1].metadata.parent_id = None

    assert elements[0].text.startswith("Hello!")
    for element in elements[:-1]:
        assert element.metadata.filename == "fake-email-attachment.msg"
        assert element.metadata.subject == "Fake email with attachment"
    assert elements[-1].text == "Hey this is a fake attachment!"
    assert elements[-1].metadata == expected_metadata


def test_partition_msg_can_process_min_max_wtih_attachments(tmp_path: pathlib.Path):
    file_path = example_doc_path("fake-email-attachment.msg")
    tmp_dir_path = str(tmp_path)
    extract_msg_attachment_info(filename=file_path, output_dir=tmp_dir_path)
    attachment_filename = str(tmp_path / str(ATTACH_EXPECTED_OUTPUT[0]["filename"]))

    attachment_elements = partition_text(
        filename=attachment_filename,
        metadata_filename=attachment_filename,
        min_partition=6,
        max_partition=12,
    )

    elements = partition_msg(
        filename=file_path,
        attachment_partitioner=partition_text,
        process_attachments=True,
        min_partition=6,
        max_partition=12,
    )

    assert elements[0].text.startswith("Hello!")
    assert elements[-1].text == attachment_elements[-1].text
    assert elements[-2].text == attachment_elements[-2].text
    for element in elements:
        if element.metadata.attached_to_filename is not None:
            assert len(element.text) <= 12
            assert len(element.text) >= 6


def test_partition_msg_raises_with_no_partitioner():
    with pytest.raises(ValueError):
        partition_msg(example_doc_path("fake-email-attachment.msg"), process_attachments=True)


def test_partition_msg_metadata_date_from_header(mocker: MockFixture):
    expected_last_modification_date = "2022-12-16T17:04:16-05:00"

    mocker.patch(
        "unstructured.partition.msg.get_last_modified_date",
        return_value=None,
    )
    mocker.patch(
        "unstructured.partition.msg.get_last_modified_date_from_file",
        return_value=None,
    )

    elements = partition_msg(example_doc_path("fake-email.msg"))

    assert elements[0].metadata.last_modified == expected_last_modification_date


def test_partition_msg_from_file_custom_metadata_date():
    expected_last_modification_date = "2020-07-05T09:24:28"

    with open(example_doc_path("fake-email.msg"), "rb") as f:
        elements = partition_msg(file=f, metadata_last_modified=expected_last_modification_date)

    assert elements[0].metadata.last_modified == expected_last_modification_date


def test_partition_msg_custom_metadata_date():
    expected_last_modification_date = "2020-07-05T09:24:28"

    elements = partition_msg(
        example_doc_path("fake-email.msg"), metadata_last_modified=expected_last_modification_date
    )

    assert elements[0].metadata.last_modified == expected_last_modification_date


def test_partition_msg_with_json():
    elements = partition_msg(example_doc_path("fake-email.msg"))
    assert_round_trips_through_JSON(elements)


def test_partition_msg_with_pgp_encrypted_message(caplog: LogCaptureFixture):
    elements = partition_msg(example_doc_path("fake-encrypted.msg"))

    assert elements == []
    assert "WARNING" in caplog.text
    assert "Encrypted email detected" in caplog.text


def test_add_chunking_strategy_by_title_on_partition_msg():
    filename = example_doc_path("fake-email.msg")

    elements = partition_msg(filename=filename)
    chunk_elements = partition_msg(filename, chunking_strategy="by_title")
    chunks = chunk_by_title(elements)

    assert chunk_elements != elements
    assert chunk_elements == chunks


def test_partition_msg_element_metadata_has_languages():
    filename = "example-docs/fake-email.msg"
    elements = partition_msg(filename=filename)
    assert elements[0].metadata.languages == ["eng"]


def test_partition_msg_respects_languages_arg():
    filename = "example-docs/fake-email.msg"
    elements = partition_msg(filename=filename, languages=["deu"])
    assert all(element.metadata.languages == ["deu"] for element in elements)


def test_partition_msg_raises_TypeError_for_invalid_languages():
    with pytest.raises(TypeError):
        filename = "example-docs/fake-email.msg"
        partition_msg(filename=filename, languages="eng")  # pyright: ignore[reportArgumentType]
