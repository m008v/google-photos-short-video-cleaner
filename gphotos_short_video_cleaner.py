#!/usr/bin/env python3
"""Google Photos short-video cleaner driven through Selenium.

The tool intentionally operates in two phases:
1. Dry-run scan: read the duration badge shown on Google Photos video tiles.
2. Optional delete: select only tiles whose displayed duration is strictly below
   the configured threshold and move them to Google Photos Trash in bounded batches.

It never empties Trash and refuses any confirmation action containing a
"permanent delete" meaning.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import os
import re
import sys
import time
import unicodedata
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlparse

SELENIUM_IMPORT_ERROR: ImportError | None = None

try:
    from selenium import webdriver
    from selenium.common.exceptions import (
        JavascriptException,
        StaleElementReferenceException,
        TimeoutException,
        WebDriverException,
    )
    from selenium.webdriver.remote.webdriver import WebDriver
    from selenium.webdriver.support.ui import WebDriverWait
except ImportError as exc:  # pragma: no cover - handled when a browser session is requested
    SELENIUM_IMPORT_ERROR = exc
    webdriver = None  # type: ignore[assignment]
    WebDriver = Any  # type: ignore[misc,assignment]
    WebDriverWait = None  # type: ignore[assignment]

    class _SeleniumUnavailableError(Exception):
        pass

    JavascriptException = _SeleniumUnavailableError
    StaleElementReferenceException = _SeleniumUnavailableError
    TimeoutException = _SeleniumUnavailableError
    WebDriverException = _SeleniumUnavailableError


APP_NAME = "Google Photos Short Video Cleaner"
DEFAULT_START_URL = "https://photos.google.com/"
CONFIRM_PHRASE = "MOVE_TO_TRASH"
LOGGER = logging.getLogger("gphotos-cleaner")

# Google Photos DOM selectors observed in current deletion tooling. Every
# destructive action is additionally checked by accessible text and context.
UNCHECKED_CHECKBOX_SELECTORS = (
    '.ckGgle[aria-checked="false"]',
    '[role="checkbox"][aria-checked="false"]',
    '[data-lat][aria-checked="false"]',
)
CHECKED_CHECKBOX_SELECTORS = (
    '.ckGgle[aria-checked="true"]',
    '[role="checkbox"][aria-checked="true"]',
    '[data-lat][aria-checked="true"]',
)


class CleanerError(RuntimeError):
    """Base error for controlled failures."""


class SafetyStop(CleanerError):
    """Raised when the UI no longer satisfies a destructive safety condition."""


@dataclass(frozen=True)
class MediaItem:
    key: str
    key_source: str
    label: str
    duration_text: str | None
    duration_seconds: int | None

    @property
    def identity(self) -> str:
        """Best available per-item identity extracted from the rendered tile."""
        return f"{self.key_source}\u241f{self.key}"

    @property
    def signature(self) -> str:
        # Retained for diagnostics; deletion allow-lists use ``identity``.
        return f"{self.identity}\u241f{self.label}\u241f{self.duration_text or ''}"


@dataclass
class ScanResult:
    threshold_seconds: float
    candidates: list[MediaItem]
    all_videos: list[MediaItem]
    videos_without_duration: list[MediaItem]
    scroll_iterations: int
    stopped_reason: str


@dataclass
class DeleteResult:
    planned: int
    deleted: list[MediaItem]
    failed_clicks: dict[str, int]
    stopped_reason: str


@dataclass(frozen=True)
class RuntimeConfig:
    threshold_seconds: float
    batch_size: int
    limit: int
    max_scrolls: int
    scroll_settle_seconds: float
    action_timeout_seconds: float


# This helper follows the media checkboxes up to their actual scrollable
# ancestor. Google Photos changes generated class names frequently, so relying
# only on a hard-coded container class makes the gallery look one-page long.
_SCROLL_TARGET_HELPER_JS = r"""
function findScrollTarget() {
  const checkboxSelector = '.ckGgle[aria-checked], [role="checkbox"][aria-checked], [data-lat][aria-checked]';
  const preferredSelectors = [
    '.yDSiEe.uGCjIb.zcLWac.eejsDc.TWmIyd',
    '.yDSiEe.uGCjIb.zcLWac',
    '[class~="zcLWac"][class~="eejsDc"]',
    '[role="main"]',
    '[role="list"]',
    '[role="grid"]'
  ];
  const candidates = [];
  const seen = new Set();

  function addCandidate(element, name) {
    if (!element || seen.has(element) || !element.isConnected) return;
    seen.add(element);
    if (element.scrollHeight <= element.clientHeight + 1 || element.clientHeight <= 0) return;
    const rect = element.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) return;
    const style = window.getComputedStyle(element);
    const scrollableStyle = /^(auto|scroll|overlay)$/.test(style.overflowY) ? 1 : 0;
    candidates.push({
      element,
      name,
      tiles: element.querySelectorAll(checkboxSelector).length,
      scrollableStyle,
      overflow: element.scrollHeight - element.clientHeight
    });
  }

  for (const selector of preferredSelectors) {
    for (const element of document.querySelectorAll(selector)) {
      addCandidate(element, selector);
    }
  }

  // The rendered tile is the most stable landmark in Google Photos. Walking
  // through its ancestors finds the virtualized scroller even after classes
  // change, as long as the gallery remains selectable.
  for (const checkbox of document.querySelectorAll(checkboxSelector)) {
    let ancestor = checkbox.parentElement;
    for (let depth = 0; ancestor && depth < 16; depth += 1, ancestor = ancestor.parentElement) {
      addCandidate(ancestor, `checkbox-ancestor-${depth}`);
    }
  }

  const doc = document.scrollingElement || document.documentElement;
  addCandidate(doc, 'document.scrollingElement');
  candidates.sort((a, b) =>
    (b.tiles - a.tiles) ||
    (b.scrollableStyle - a.scrollableStyle) ||
    (b.overflow - a.overflow)
  );
  if (candidates.length > 0) return candidates[0];
  return doc ? { element: doc, name: 'document.scrollingElement', overflow: 0 } : null;
}
"""


# This script is injected only to inspect the already-rendered DOM. It does
# not call internal Google APIs and does not access media bytes.
SNAPSHOT_JS = _SCROLL_TARGET_HELPER_JS + r"""
const threshold = Number(arguments[0]);
const includeChecked = Boolean(arguments[1]);
const includeElements = Boolean(arguments[2]);

const uncheckedSelectors = [
  '.ckGgle[aria-checked="false"]',
  '[role="checkbox"][aria-checked="false"]',
  '[data-lat][aria-checked="false"]'
];
const checkedSelectors = [
  '.ckGgle[aria-checked="true"]',
  '[role="checkbox"][aria-checked="true"]',
  '[data-lat][aria-checked="true"]'
];
const videoTokens = ['video', 'vidéo', '動画', '视频', '影片', '비디오'];

function normalizeText(value) {
  return String(value || '')
    .toLowerCase()
    .replace(/đ/g, 'd')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .normalize('NFC')
    .replace(/[\u2019']/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

function queryUnique(selectors, root = document) {
  const out = [];
  const seen = new Set();
  for (const selector of selectors) {
    for (const element of root.querySelectorAll(selector)) {
      if (!seen.has(element)) {
        seen.add(element);
        out.push(element);
      }
    }
  }
  return out;
}

function isVisible(element, requireViewport = false) {
  if (!element || !element.isConnected || element.hidden) return false;
  const style = window.getComputedStyle(element);
  if (style.display === 'none' || style.visibility === 'hidden' || style.opacity === '0') return false;
  const rect = element.getBoundingClientRect();
  if (rect.width <= 0 || rect.height <= 0) return false;
  if (requireViewport) {
    if (rect.bottom < -2 || rect.right < -2 || rect.top > window.innerHeight + 2 || rect.left > window.innerWidth + 2) {
      return false;
    }
  }
  return true;
}

function parseDuration(value) {
  const normalized = String(value || '').trim().replace(/：/g, ':');
  if (!/^\d{1,3}:[0-5]\d(?::[0-5]\d)?$/.test(normalized)) return null;
  const parts = normalized.split(':').map(Number);
  if (parts.length === 2) return parts[0] * 60 + parts[1];
  return parts[0] * 3600 + parts[1] * 60 + parts[2];
}

function isVideoLabel(label) {
  const firstSegment = normalizeText(String(label || '').split(/[-–—]/)[0]);
  if (!firstSegment) return false;
  return videoTokens.some(token => {
    const t = normalizeText(token);
    return firstSegment === t || firstSegment.startsWith(t + ' ') ||
      firstSegment.startsWith(t + ',') || firstSegment.startsWith(t + ':') ||
      firstSegment.startsWith(t + '•') || firstSegment.startsWith(t + '|');
  });
}

function findMediaTile(checkbox) {
  let node = checkbox.parentElement;
  for (let depth = 0; node && depth < 8; depth += 1, node = node.parentElement) {
    const anchor = node.querySelector('a[href*="/photo/"]');
    if (anchor && countTileCheckboxes(node) <= 1) return node;
  }
  return checkbox.parentElement || checkbox;
}

function findLabelledTile(checkbox) {
  let node = checkbox;
  for (let depth = 0; node && depth < 12; depth += 1, node = node.parentElement) {
    const label = node.getAttribute && node.getAttribute('aria-label');
    if (label && isVideoLabel(label)) return { tile: findMediaTile(checkbox), label };
  }
  return null;
}

function collectDurationBadges(scope, tile) {
  const out = [];
  const walker = document.createTreeWalker(scope, NodeFilter.SHOW_TEXT);
  const tileRect = tile.getBoundingClientRect();
  let textNode;
  while ((textNode = walker.nextNode())) {
    const raw = String(textNode.nodeValue || '').trim().replace(/：/g, ':');
    const seconds = parseDuration(raw);
    if (seconds === null) continue;
    const parent = textNode.parentElement;
    if (!isVisible(parent)) continue;
    const rect = parent.getBoundingClientRect();
    // Duration badges are compact and rendered inside the thumbnail tile.
    if (rect.width > 220 || rect.height > 90) continue;
    const cx = rect.left + rect.width / 2;
    const cy = rect.top + rect.height / 2;
    if (cx < tileRect.left - 4 || cx > tileRect.right + 4 || cy < tileRect.top - 4 || cy > tileRect.bottom + 4) continue;
    // Google Photos normally places duration at the lower-right. Prefer that
    // over other time-like text such as capture time near the tile header.
    const dx = tileRect.right - cx;
    const dy = tileRect.bottom - cy;
    out.push({ text: raw, seconds, distance: Math.hypot(dx, dy) });
  }
  out.sort((a, b) => a.distance - b.distance);
  return out;
}

function countTileCheckboxes(scope) {
  return queryUnique(uncheckedSelectors.concat(checkedSelectors), scope).length;
}

function findDuration(tile, checkbox) {
  let scope = tile;
  for (let depth = 0; scope && depth < 5; depth += 1, scope = scope.parentElement) {
    const checkboxCount = countTileCheckboxes(scope);
    if (checkboxCount > 3) break;
    const badges = collectDurationBadges(scope, tile);
    if (badges.length > 0) return badges[0];
  }
  return null;
}

function itemKey(tile, label) {
  const anchor = tile.closest('a[href*="/photo/"]') || tile.querySelector('a[href*="/photo/"]');
  if (anchor && anchor.href) return { key: anchor.href, source: 'photo-href' };

  const attributeNames = ['data-id', 'data-item-id', 'data-media-key', 'data-photo-id'];
  let node = tile;
  for (let depth = 0; node && depth < 5; depth += 1, node = node.parentElement) {
    for (const name of attributeNames) {
      const value = node.getAttribute && node.getAttribute(name);
      if (value) return { key: `${name}:${value}`, source: name };
    }
  }

  const image = tile.querySelector('img[src]');
  if (image) {
    const src = image.currentSrc || image.src;
    if (src) return { key: src, source: 'image-src' };
  }
  return { key: label, source: 'aria-label' };
}

const selectors = includeChecked ? uncheckedSelectors.concat(checkedSelectors) : uncheckedSelectors;
const checkboxes = queryUnique(selectors);
const items = [];
let videoTiles = 0;
let videosWithDuration = 0;

for (const checkbox of checkboxes) {
  const labelled = findLabelledTile(checkbox);
  if (!labelled) continue;
  videoTiles += 1;
  const duration = findDuration(labelled.tile, checkbox);
  if (duration) videosWithDuration += 1;
  const keyInfo = itemKey(labelled.tile, labelled.label);
  const item = {
    key: keyInfo.key,
    key_source: keyInfo.source,
    label: labelled.label,
    duration_text: duration ? duration.text : null,
    duration_seconds: duration ? duration.seconds : null,
    is_candidate: Boolean(duration && duration.seconds < threshold)
  };
  if (includeElements && item.is_candidate && checkbox.getAttribute('aria-checked') === 'false') {
    item.checkbox = checkbox;
  }
  items.push(item);
}

const target = findScrollTarget();
const scroll = target ? {
  name: target.name,
  top: Number(target.element.scrollTop || 0),
  height: Number(target.element.scrollHeight || 0),
  client: Number(target.element.clientHeight || window.innerHeight || 0),
  at_bottom: Number(target.element.scrollTop || 0) + Number(target.element.clientHeight || 0) + 4 >= Number(target.element.scrollHeight || 0)
} : { name: 'none', top: 0, height: 0, client: 0, at_bottom: true };

return {
  items,
  stats: {
    checkbox_count: checkboxes.length,
    video_tiles: videoTiles,
    videos_with_duration: videosWithDuration
  },
  scroll
};
"""

GET_SCROLL_STATE_JS = _SCROLL_TARGET_HELPER_JS + r"""
const target = findScrollTarget();
if (!target) return { name: 'none', top: 0, height: 0, client: 0, at_bottom: true };
const e = target.element;
return {
  name: target.name,
  top: Number(e.scrollTop || 0),
  height: Number(e.scrollHeight || 0),
  client: Number(e.clientHeight || window.innerHeight || 0),
  at_bottom: Number(e.scrollTop || 0) + Number(e.clientHeight || 0) + 4 >= Number(e.scrollHeight || 0)
};
"""

SCROLL_TO_TOP_JS = _SCROLL_TARGET_HELPER_JS + r"""
const target = findScrollTarget();
if (target) target.element.scrollTo({top: 0, left: 0, behavior: 'auto'});
return Boolean(target);
"""

SCROLL_BY_JS = _SCROLL_TARGET_HELPER_JS + r"""
const step = Number(arguments[0]);
const target = findScrollTarget();
if (!target) return false;
target.element.scrollBy({top: step, left: 0, behavior: 'auto'});
return true;
"""

SELECTED_COUNT_JS = r"""
const counterSelectors = ['.rtExYb', '[data-selection-count]', '.Mfixef .rtExYb'];
function visible(e) {
  if (!e || !e.isConnected || e.hidden) return false;
  const s = getComputedStyle(e);
  const r = e.getBoundingClientRect();
  return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
}
for (const selector of counterSelectors) {
  for (const e of document.querySelectorAll(selector)) {
    if (!visible(e)) continue;
    const text = String(e.textContent || '');
    const digits = text.replace(/[^0-9]/g, '');
    if (digits) return {count:Number(digits), source:selector, text};
  }
}
const checkedSelectors = [
  '.ckGgle[aria-checked="true"]',
  '[role="checkbox"][aria-checked="true"]',
  '[data-lat][aria-checked="true"]'
];
const unique = new Set();
for (const selector of checkedSelectors) {
  for (const e of document.querySelectorAll(selector)) unique.add(e);
}
return {count:unique.size, source:'rendered-checked-checkboxes', text:''};
"""

FIND_TOOLBAR_DELETE_JS = r"""
function norm(value) {
  return String(value || '').toLowerCase().replace(/đ/g, 'd').normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').normalize('NFC')
    .replace(/[\u2019']/g, ' ').replace(/\s+/g, ' ').trim();
}
function visible(e) {
  if (!e || !e.isConnected || e.hidden || e.disabled || e.getAttribute('aria-disabled') === 'true') return false;
  const s = getComputedStyle(e); const r = e.getBoundingClientRect();
  return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0.01 &&
    s.pointerEvents !== 'none' && r.width > 0 && r.height > 0 &&
    r.bottom >= -2 && r.right >= -2 && r.top <= window.innerHeight + 2 && r.left <= window.innerWidth + 2;
}
function textOf(e) {
  return [e.getAttribute('aria-label'), e.getAttribute('data-tooltip'), e.getAttribute('title'), e.textContent]
    .filter(Boolean).join(' ');
}
function hasPhrase(text, phrase) {
  const p = norm(phrase);
  if (!p) return false;
  // CJK labels commonly have no spaces; Latin labels must match token/phrase boundaries.
  if (/[^\x00-\x7F]/.test(p)) return text.includes(p);
  return (` ${text} `).includes(` ${p} `);
}
function insideDialog(e) { return Boolean(e.closest('[role="dialog"], [role="alertdialog"], [aria-modal="true"]')); }
const positives = ['move to trash','move to bin','chuyen vao thung rac','thung rac','delete','trash','bin','xoa','papelera','corbeille','papierkorb','cestino','lixeira','prullenbak','ゴミ箱','削除','휴지통','삭제','回收站','删除','刪除'];
const negatives = ['cancel','dismiss','close','huy','dong','quay lai','remove from album','xoa khoi album','xoa khoi thiet bi','delete from device','empty trash','empty bin','don sach thung rac','delete permanently','permanent','xoa vinh vien','restore','khoi phuc'];
const exactRules = [
  {selector:'button[data-delete-origin]', structural:true},
  {selector:'div[data-delete-origin] > button', structural:true},
  {selector:'button[aria-label="Move to trash"]', structural:false},
  {selector:'button[aria-label="Move to bin"]', structural:false},
  {selector:'button[aria-label="Delete"]', structural:false},
  {selector:'button[aria-label="Chuyển vào thùng rác"]', structural:false},
  {selector:'button[aria-label="Xoá"]', structural:false},
  {selector:'button[aria-label="Xóa"]', structural:false}
];
const exactCandidates = [];
const exactSeen = new Set();
for (const rule of exactRules) {
  for (const e of document.querySelectorAll(rule.selector)) {
    if (!visible(e) || insideDialog(e) || exactSeen.has(e)) continue;
    const raw = textOf(e); const text = norm(raw);
    if (negatives.some(k => hasPhrase(text, k))) continue;
    if (rule.structural && !positives.some(k => hasPhrase(text, k))) continue;
    exactSeen.add(e);
    exactCandidates.push({element:e, label:raw, selector:rule.selector, score:1000});
  }
}
if (exactCandidates.length === 1) return {status:'ok', ...exactCandidates[0]};
if (exactCandidates.length > 1) {
  return {status:'ambiguous', observations:exactCandidates.slice(0,5).map(x => ({label:x.label, selector:x.selector, score:x.score}))};
}
const scored = [];
for (const e of document.querySelectorAll('button, [role="button"]')) {
  if (!visible(e) || insideDialog(e)) continue;
  const raw = textOf(e); const text = norm(raw);
  if (!text) continue;
  let score = 0;
  if (positives.some(k => hasPhrase(text, k))) score += 100;
  if (e.closest('[role="toolbar"], header')) score += 20;
  if (negatives.some(k => hasPhrase(text, k))) score -= 1000;
  if (score > 0) scored.push({element:e, label:raw, selector:'accessible-text', score});
}
scored.sort((a,b) => b.score-a.score);
if (scored.length === 0) return {status:'not_found', observations:[]};
if (scored.length > 1 && scored[0].score === scored[1].score) {
  return {status:'ambiguous', observations:scored.slice(0,5).map(x => ({label:x.label, score:x.score}))};
}
return {status:'ok', element:scored[0].element, label:scored[0].label, selector:scored[0].selector, score:scored[0].score};
"""

FIND_CONFIRM_ACTION_JS = r"""
function norm(value) {
  return String(value || '').toLowerCase().replace(/đ/g, 'd').normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').normalize('NFC')
    .replace(/[\u2019']/g, ' ').replace(/\s+/g, ' ').trim();
}
function visible(e) {
  if (!e || !e.isConnected || e.hidden || e.disabled || e.getAttribute('aria-disabled') === 'true') return false;
  const s = getComputedStyle(e); const r = e.getBoundingClientRect();
  return s.display !== 'none' && s.visibility !== 'hidden' && Number(s.opacity || 1) > 0.01 &&
    s.pointerEvents !== 'none' && r.width > 0 && r.height > 0 &&
    r.bottom >= -2 && r.right >= -2 && r.top <= window.innerHeight + 2 && r.left <= window.innerWidth + 2;
}
function textOf(e) {
  return [e.getAttribute('aria-label'), e.getAttribute('data-tooltip'), e.getAttribute('title'), e.textContent]
    .filter(Boolean).join(' ');
}
function hasPhrase(text, phrase) {
  const p = norm(phrase);
  if (!p) return false;
  // CJK labels commonly have no spaces; Latin labels must match token/phrase boundaries.
  if (/[^\x00-\x7F]/.test(p)) return text.includes(p);
  return (` ${text} `).includes(` ${p} `);
}
const dialogs = [...document.querySelectorAll('[role="dialog"], [role="alertdialog"], [aria-modal="true"]')].filter(visible);
if (dialogs.length === 0) return {status:'dialog_not_found'};
if (dialogs.length > 1) return {status:'dialog_ambiguous', count:dialogs.length};
const dialog = dialogs[0];
const permanent = ['delete permanently','permanently delete','xoa vinh vien','xoa han','delete forever'];
const cancel = ['cancel','dismiss','close','huy','dong','quay lai','khong'];
const positiveExact = ['move to trash','move to bin','chuyen vao thung rac','delete','xoa'];
const buttons = [...dialog.querySelectorAll('button, [role="button"]')].filter(visible);
const observed = buttons.map(e => ({element:e, raw:textOf(e), text:norm(textOf(e))}));
for (const item of observed) {
  if (permanent.some(k => hasPhrase(item.text, k))) {
    return {status:'permanent_delete_refused', label:item.raw, dialog_text:String(dialog.textContent || '').trim().slice(0,1000)};
  }
}
const scored = [];
for (const item of observed) {
  let score = 0;
  if (positiveExact.some(k => item.text === norm(k))) score += 300;
  else if (positiveExact.some(k => hasPhrase(item.text, k))) score += 100;
  if (cancel.some(k => hasPhrase(item.text, k))) score -= 1000;
  if (score > 0) scored.push({...item, score});
}
scored.sort((a,b) => b.score-a.score);
if (scored.length === 0) {
  return {status:'confirm_not_found', observations:observed.map(x => x.raw)};
}
if (scored.length > 1 && scored[0].score === scored[1].score) {
  return {status:'confirm_ambiguous', observations:scored.map(x => ({label:x.raw, score:x.score}))};
}
return {status:'ok', element:scored[0].element, label:scored[0].raw, dialog_text:String(dialog.textContent || '').trim().slice(0,1000)};
"""

DIALOG_VISIBLE_JS = r"""
function visible(e) {
  if (!e || !e.isConnected || e.hidden) return false;
  const s = getComputedStyle(e); const r = e.getBoundingClientRect();
  return s.display !== 'none' && s.visibility !== 'hidden' && r.width > 0 && r.height > 0;
}
return [...document.querySelectorAll('[role="dialog"], [role="alertdialog"], [aria-modal="true"]')].some(visible);
"""

VIDEO_TILE_COUNT_JS = r"""
const tokens = ['video', 'vidéo', '動画', '视频', '影片', '비디오'];
function normalizeText(value) {
  return String(value || '').toLowerCase().replace(/đ/g, 'd').normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').normalize('NFC').replace(/\s+/g, ' ').trim();
}
let count = 0;
const seen = new Set();
for (const element of document.querySelectorAll('.ckGgle[aria-checked], [role="checkbox"][aria-checked], [data-lat][aria-checked]')) {
  if (seen.has(element)) continue;
  seen.add(element);
  const label = normalizeText(element.getAttribute('aria-label'));
  if (tokens.some(token => label === normalizeText(token) || label.startsWith(normalizeText(token) + ' ') || label.startsWith(normalizeText(token) + ' -'))) {
    count += 1;
  }
}
return count;
"""

FIND_VIDEO_NAV_ELEMENT_JS = r"""
const tokens = ['video', 'videos', 'vidéo', 'vidéos', '動画', '视频', '影片', '비디오'];
function normalizeText(value) {
  return String(value || '').toLowerCase().replace(/đ/g, 'd').normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '').normalize('NFC').replace(/\s+/g, ' ').trim();
}
for (const anchor of document.querySelectorAll('a[href]')) {
  const label = normalizeText(anchor.getAttribute('aria-label') || anchor.textContent);
  if (tokens.some(token => label === normalizeText(token))) return anchor;
}
return null;
"""


_DURATION_RE = re.compile(r"^\d{1,3}:[0-5]\d(?::[0-5]\d)?$")


def duration_text_to_seconds(value: str) -> int:
    """Parse m:ss or h:mm:ss as shown by the Google Photos tile badge."""
    normalized = value.strip().replace("：", ":")
    if not _DURATION_RE.fullmatch(normalized):
        raise ValueError(f"Thời lượng không hợp lệ: {value!r}")
    parts = [int(part) for part in normalized.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def normalize_text(value: str) -> str:
    decomposed = unicodedata.normalize("NFD", value.lower().replace("đ", "d"))
    stripped = "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn")
    return " ".join(unicodedata.normalize("NFC", stripped).replace("’", " ").replace("'", " ").split())


def _to_media_item(raw: dict[str, Any]) -> MediaItem:
    return MediaItem(
        key=str(raw.get("key") or raw.get("label") or "unknown"),
        key_source=str(raw.get("key_source") or "unknown"),
        label=str(raw.get("label") or ""),
        duration_text=(str(raw["duration_text"]) if raw.get("duration_text") is not None else None),
        duration_seconds=(int(raw["duration_seconds"]) if raw.get("duration_seconds") is not None else None),
    )


def _dedupe_items(items: Iterable[MediaItem]) -> list[MediaItem]:
    out: dict[str, MediaItem] = {}
    for item in items:
        out.setdefault(item.identity, item)
    return list(out.values())


def _record_scan_item(
    item: MediaItem,
    threshold_seconds: float,
    all_seen: dict[str, MediaItem],
    candidate_seen: dict[str, MediaItem],
    no_duration_seen: dict[str, MediaItem],
) -> None:
    """Keep the strongest observation as virtualized tiles enter the viewport."""
    identity = item.identity
    previous = all_seen.get(identity)
    if previous is None or (previous.duration_seconds is None and item.duration_seconds is not None):
        all_seen[identity] = item

    if item.duration_seconds is None:
        if all_seen[identity].duration_seconds is None:
            no_duration_seen.setdefault(identity, item)
        return

    no_duration_seen.pop(identity, None)
    if item.duration_seconds < threshold_seconds:
        candidate_seen.setdefault(identity, item)


def assert_safe_page_context(driver: WebDriver) -> None:
    """Fail closed outside Google Photos or on routes with destructive ambiguity."""
    current_url = str(getattr(driver, "current_url", "") or "")
    parsed = urlparse(current_url)
    host = (parsed.hostname or "").lower()
    path = (parsed.path or "/").lower()
    if host != "photos.google.com":
        raise SafetyStop(f"Trang hiện tại không thuộc photos.google.com: {current_url!r}")

    blocked_fragments = (
        "/trash",
        "/bin",
        "/album/",
        "/sharing",
        "/shared",
        "/partner-sharing",
    )
    blocked = next((fragment for fragment in blocked_fragments if fragment in path), None)
    if blocked:
        raise SafetyStop(
            f"Đường dẫn hiện tại ({path}) chứa vùng bị chặn {blocked!r}. "
            "Hãy quay lại Google Photos > Tìm kiếm > Video rồi chạy lại."
        )


def get_scroll_state(driver: WebDriver) -> dict[str, Any]:
    state = driver.execute_script(GET_SCROLL_STATE_JS)
    if not isinstance(state, dict):
        raise CleanerError("Không đọc được trạng thái cuộn của Google Photos.")
    return state


def get_selected_count(driver: WebDriver) -> tuple[int, str]:
    result = driver.execute_script(SELECTED_COUNT_JS)
    if not isinstance(result, dict):
        return 0, "unknown"
    return int(result.get("count") or 0), str(result.get("source") or "unknown")


def take_snapshot(
    driver: WebDriver,
    threshold_seconds: float,
    *,
    include_checked: bool,
    include_elements: bool,
) -> dict[str, Any]:
    result = driver.execute_script(
        SNAPSHOT_JS,
        threshold_seconds,
        include_checked,
        include_elements,
    )
    if not isinstance(result, dict):
        raise CleanerError("Không đọc được danh sách video từ DOM Google Photos.")
    return result


def scroll_to_top(driver: WebDriver, settle_seconds: float) -> None:
    driver.execute_script(SCROLL_TO_TOP_JS)
    try:
        WebDriverWait(driver, 3, poll_frequency=0.1).until(
            lambda d: float(get_scroll_state(d).get("top") or 0) <= 1
        )
    except TimeoutException:
        LOGGER.warning("Không xác nhận được vị trí đầu trang; vẫn tiếp tục quét.")
    time.sleep(settle_seconds)


def scroll_forward(driver: WebDriver, state: dict[str, Any], settle_seconds: float) -> bool:
    before_top = float(state.get("top") or 0)
    before_height = float(state.get("height") or 0)
    client = float(state.get("client") or 800)
    step = max(250, int(client * 0.55))
    driver.execute_script(SCROLL_BY_JS, step)

    moved = False
    try:
        WebDriverWait(driver, max(1.5, settle_seconds * 4), poll_frequency=0.15).until(
            lambda d: (
                float(get_scroll_state(d).get("top") or 0) > before_top + 1
                or float(get_scroll_state(d).get("height") or 0) > before_height + 1
            )
        )
        moved = True
    except TimeoutException:
        pass
    time.sleep(settle_seconds)
    after = get_scroll_state(driver)
    return moved or float(after.get("top") or 0) > before_top + 1 or float(after.get("height") or 0) > before_height + 1


def scan_gallery(driver: WebDriver, config: RuntimeConfig) -> ScanResult:
    LOGGER.info("Bắt đầu dry-run: chỉ đọc DOM, không nhấp chọn hoặc xoá.")
    assert_safe_page_context(driver)
    scroll_to_top(driver, config.scroll_settle_seconds)

    all_seen: dict[str, MediaItem] = {}
    candidate_seen: dict[str, MediaItem] = {}
    no_duration_seen: dict[str, MediaItem] = {}
    stable_bottom_rounds = 0
    stopped_reason = "max-scrolls"
    iterations = 0

    for iterations in range(1, config.max_scrolls + 1):
        snapshot = take_snapshot(
            driver,
            config.threshold_seconds,
            include_checked=True,
            include_elements=False,
        )
        raw_items = snapshot.get("items") or []
        for raw in raw_items:
            item = _to_media_item(raw)
            _record_scan_item(
                item,
                config.threshold_seconds,
                all_seen,
                candidate_seen,
                no_duration_seen,
            )

        state = snapshot.get("scroll") or get_scroll_state(driver)
        if iterations == 1 and int((snapshot.get("stats") or {}).get("video_tiles") or 0) == 0:
            LOGGER.warning(
                "Không thấy tile Video ở màn hình hiện tại. Hãy kiểm tra bạn đã mở mục Video trong Google Photos."
            )

        if iterations == 1 or iterations % 10 == 0 or bool(state.get("at_bottom")):
            LOGGER.info(
                "Quét %s vòng | video nhận diện: %s | dưới %.3gs: %s | vị trí: %.0f/%.0f",
                iterations,
                len(all_seen),
                config.threshold_seconds,
                len(candidate_seen),
                float(state.get("top") or 0),
                float(state.get("height") or 0),
            )

        if bool(state.get("at_bottom")):
            before_count = len(all_seen)
            before_height = float(state.get("height") or 0)
            time.sleep(max(0.5, config.scroll_settle_seconds))
            settle_snapshot = take_snapshot(
                driver,
                config.threshold_seconds,
                include_checked=True,
                include_elements=False,
            )
            for raw in settle_snapshot.get("items") or []:
                item = _to_media_item(raw)
                _record_scan_item(
                    item,
                    config.threshold_seconds,
                    all_seen,
                    candidate_seen,
                    no_duration_seen,
                )
            settle_state = settle_snapshot.get("scroll") or get_scroll_state(driver)
            if len(all_seen) == before_count and float(settle_state.get("height") or 0) <= before_height + 1:
                stable_bottom_rounds += 1
            else:
                stable_bottom_rounds = 0
            if stable_bottom_rounds >= 3:
                stopped_reason = "end-of-gallery"
                break
        else:
            stable_bottom_rounds = 0

        moved = scroll_forward(driver, state, config.scroll_settle_seconds)
        if not moved and bool(get_scroll_state(driver).get("at_bottom")):
            stable_bottom_rounds += 1
            if stable_bottom_rounds >= 3:
                stopped_reason = "end-of-gallery"
                break

    return ScanResult(
        threshold_seconds=config.threshold_seconds,
        candidates=list(candidate_seen.values()),
        all_videos=list(all_seen.values()),
        videos_without_duration=list(no_duration_seen.values()),
        scroll_iterations=iterations,
        stopped_reason=stopped_reason,
    )


def _wait_for_selection_increase(driver: WebDriver, before: int, timeout: float = 2.5) -> bool:
    try:
        WebDriverWait(driver, timeout, poll_frequency=0.1).until(
            lambda d: get_selected_count(d)[0] > before
        )
        return True
    except TimeoutException:
        return False


def _click_candidate_checkbox(driver: WebDriver, checkbox: Any) -> bool:
    before, _ = get_selected_count(driver)
    try:
        driver.execute_script("arguments[0].click();", checkbox)
    except (JavascriptException, StaleElementReferenceException, WebDriverException):
        return False
    return _wait_for_selection_increase(driver, before)


def _find_toolbar_delete(driver: WebDriver) -> dict[str, Any] | None:
    result = driver.execute_script(FIND_TOOLBAR_DELETE_JS)
    return result if isinstance(result, dict) else None


def _find_confirm_action(driver: WebDriver) -> dict[str, Any] | None:
    result = driver.execute_script(FIND_CONFIRM_ACTION_JS)
    return result if isinstance(result, dict) else None


def move_current_selection_to_trash(
    driver: WebDriver,
    expected_count: int,
    timeout_seconds: float,
) -> None:
    assert_safe_page_context(driver)
    if bool(driver.execute_script(DIALOG_VISIBLE_JS)):
        raise SafetyStop("Đang có sẵn một hộp thoại trên trang; tool không nhấp nút xoá phía sau hộp thoại.")

    actual_count, source = get_selected_count(driver)
    if actual_count != expected_count:
        raise SafetyStop(
            f"Số mục đang chọn ({actual_count}, nguồn {source}) không khớp số mục tool theo dõi "
            f"({expected_count}). Đã dừng để tránh xoá nhầm."
        )

    try:
        toolbar = WebDriverWait(driver, timeout_seconds, poll_frequency=0.2).until(
            lambda d: (
                result
                if (result := _find_toolbar_delete(d)) and result.get("status") == "ok"
                else False
            )
        )
    except TimeoutException as exc:
        diagnostic = _find_toolbar_delete(driver)
        raise SafetyStop(
            "Không xác định chắc chắn được nút Chuyển vào thùng rác. "
            f"Chẩn đoán: {json.dumps(diagnostic, ensure_ascii=False, default=str)}"
        ) from exc

    LOGGER.info("Nút xoá được nhận diện: %s", toolbar.get("label") or toolbar.get("selector"))
    driver.execute_script("arguments[0].click();", toolbar["element"])

    try:
        confirmation = WebDriverWait(driver, timeout_seconds, poll_frequency=0.2).until(
            lambda d: (
                result
                if (result := _find_confirm_action(d)) and result.get("status") in {
                    "ok",
                    "permanent_delete_refused",
                    "dialog_ambiguous",
                    "confirm_ambiguous",
                    "confirm_not_found",
                }
                else False
            )
        )
    except TimeoutException as exc:
        raise SafetyStop("Hộp thoại xác nhận không xuất hiện hoặc DOM đã thay đổi; tool không nhấp tiếp.") from exc

    status = str(confirmation.get("status") or "unknown")
    if status == "permanent_delete_refused":
        raise SafetyStop(
            "Google Photos đang yêu cầu Xoá vĩnh viễn (thường do Thùng rác đầy). "
            "Tool đã từ chối thao tác này."
        )
    if status != "ok":
        raise SafetyStop(
            "Không xác định duy nhất được nút xác nhận Chuyển vào thùng rác. "
            f"Chẩn đoán: {json.dumps(confirmation, ensure_ascii=False, default=str)}"
        )

    LOGGER.info("Nút xác nhận được nhận diện: %s", confirmation.get("label"))
    driver.execute_script("arguments[0].click();", confirmation["element"])

    try:
        WebDriverWait(driver, timeout_seconds, poll_frequency=0.2).until(
            lambda d: get_selected_count(d)[0] == 0
        )
    except TimeoutException as exc:
        raise CleanerError(
            "Đã nhấp xác nhận nhưng bộ đếm mục chọn không trở về 0; không thể chứng minh lô đã hoàn tất."
        ) from exc

    try:
        WebDriverWait(driver, min(timeout_seconds, 5), poll_frequency=0.2).until_not(
            lambda d: bool(d.execute_script(DIALOG_VISIBLE_JS))
        )
    except TimeoutException:
        LOGGER.warning("Hộp thoại chưa biến mất sau khi bộ đếm đã về 0.")


def delete_candidates(
    driver: WebDriver,
    config: RuntimeConfig,
    planned_items: Iterable[MediaItem],
) -> DeleteResult:
    plan = [item for item in _dedupe_items(planned_items) if item.key_source != "aria-label"]
    if config.limit > 0:
        plan = plan[: config.limit]
    target = len(plan)
    if target <= 0:
        return DeleteResult(planned=0, deleted=[], failed_clicks={}, stopped_reason="nothing-to-delete")

    allowed_identities = {item.identity for item in plan}
    assert_safe_page_context(driver)
    selected_at_start, _ = get_selected_count(driver)
    if selected_at_start != 0:
        raise SafetyStop(
            f"Google Photos đang có sẵn {selected_at_start} mục được chọn. Hãy bỏ chọn tất cả rồi chạy lại."
        )

    deleted: list[MediaItem] = []
    failed_clicks: dict[str, int] = {}
    globally_deleted_identities: set[str] = set()
    stopped_reason = "target-reached"

    while len(deleted) < target:
        assert_safe_page_context(driver)
        remaining = target - len(deleted)
        batch_target = min(config.batch_size, remaining)
        scroll_to_top(driver, config.scroll_settle_seconds)
        batch: list[MediaItem] = []
        batch_identities: set[str] = set()
        stable_bottom_rounds = 0
        batch_end_reached = False

        for iteration in range(1, config.max_scrolls + 1):
            snapshot = take_snapshot(
                driver,
                config.threshold_seconds,
                include_checked=False,
                include_elements=True,
            )
            raw_items = snapshot.get("items") or []

            for raw in raw_items:
                if not raw.get("is_candidate") or raw.get("checkbox") is None:
                    continue
                item = _to_media_item(raw)
                if item.identity not in allowed_identities:
                    continue
                if item.identity in globally_deleted_identities or item.identity in batch_identities:
                    continue
                if failed_clicks.get(item.identity, 0) >= 3:
                    continue

                if _click_candidate_checkbox(driver, raw["checkbox"]):
                    batch.append(item)
                    batch_identities.add(item.identity)
                    LOGGER.info(
                        "Đã chọn %s/%s trong lô: %s (%s)",
                        len(batch),
                        batch_target,
                        item.duration_text,
                        item.label,
                    )
                else:
                    failed_clicks[item.identity] = failed_clicks.get(item.identity, 0) + 1
                    LOGGER.warning(
                        "Không chọn được tile (%s/3): %s",
                        failed_clicks[item.identity],
                        item.label,
                    )

                if len(batch) >= batch_target:
                    break

            if len(batch) >= batch_target:
                break

            state = snapshot.get("scroll") or get_scroll_state(driver)
            if bool(state.get("at_bottom")):
                stable_bottom_rounds += 1
                if stable_bottom_rounds >= 3:
                    batch_end_reached = True
                    break
                time.sleep(max(0.5, config.scroll_settle_seconds))
            else:
                stable_bottom_rounds = 0

            moved = scroll_forward(driver, state, config.scroll_settle_seconds)
            if not moved and bool(get_scroll_state(driver).get("at_bottom")):
                stable_bottom_rounds += 1
                if stable_bottom_rounds >= 3:
                    batch_end_reached = True
                    break

        if not batch:
            stopped_reason = "no-more-matching-videos"
            break

        actual_selected, source = get_selected_count(driver)
        if actual_selected != len(batch):
            raise SafetyStop(
                f"Trước khi xoá, bộ đếm Google Photos là {actual_selected} ({source}) nhưng tool chỉ theo dõi "
                f"{len(batch)} mục. Đã dừng để tránh xoá mục ngoài danh sách."
            )

        assert_safe_page_context(driver)
        LOGGER.info("Chuyển lô %s video vào Thùng rác...", len(batch))
        move_current_selection_to_trash(driver, len(batch), config.action_timeout_seconds)
        deleted.extend(batch)
        globally_deleted_identities.update(batch_identities)
        LOGGER.info("Đã hoàn tất %s/%s video dự kiến.", len(deleted), target)
        time.sleep(max(0.5, config.scroll_settle_seconds))

        if batch_end_reached and len(batch) < batch_target:
            # One final restart from the top is still performed by the while loop.
            LOGGER.info("Đã chạm cuối thư viện; kiểm tra lại từ đầu sau khi xoá lô cuối.")

    return DeleteResult(
        planned=target,
        deleted=deleted,
        failed_clicks=failed_clicks,
        stopped_reason=stopped_reason,
    )


def timestamp_slug() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S_%f")


def write_scan_reports(result: ScanResult, output_dir: Path) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    slug = timestamp_slug()
    csv_path = output_dir / f"scan_short_videos_{slug}.csv"
    json_path = output_dir / f"scan_short_videos_{slug}.json"

    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "duration_text",
                "duration_seconds_displayed",
                "label",
                "key_source",
                "key",
            ],
        )
        writer.writeheader()
        for item in sorted(
            result.candidates,
            key=lambda x: (x.duration_seconds if x.duration_seconds is not None else 10**9, x.label),
        ):
            writer.writerow(
                {
                    "duration_text": item.duration_text,
                    "duration_seconds_displayed": item.duration_seconds,
                    "label": item.label,
                    "key_source": item.key_source,
                    "key": item.key,
                }
            )

    payload = {
        "generated_at": datetime.now().astimezone().isoformat(),
        "threshold_seconds": result.threshold_seconds,
        "candidate_count": len(result.candidates),
        "video_count_observed": len(result.all_videos),
        "videos_without_duration_count": len(result.videos_without_duration),
        "scroll_iterations": result.scroll_iterations,
        "stopped_reason": result.stopped_reason,
        "candidates": [asdict(item) for item in result.candidates],
        "videos_without_duration": [asdict(item) for item in result.videos_without_duration],
    }
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return csv_path, json_path


def write_delete_report(result: DeleteResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"deleted_short_videos_{timestamp_slug()}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "status",
                "duration_text",
                "duration_seconds_displayed",
                "label",
                "key_source",
                "key",
            ],
        )
        writer.writeheader()
        for item in result.deleted:
            writer.writerow(
                {
                    "status": "moved_to_trash",
                    "duration_text": item.duration_text,
                    "duration_seconds_displayed": item.duration_seconds,
                    "label": item.label,
                    "key_source": item.key_source,
                    "key": item.key,
                }
            )
    return path


def build_driver(args: argparse.Namespace) -> WebDriver:
    if SELENIUM_IMPORT_ERROR is not None or webdriver is None:
        raise CleanerError(
            "Thiếu Selenium. Hãy chạy: python -m pip install -r requirements.txt"
        ) from SELENIUM_IMPORT_ERROR

    # Disable Selenium Manager's optional anonymous statistics for this local tool.
    os.environ.setdefault("SE_AVOID_STATS", "true")

    options = webdriver.ChromeOptions()
    options.page_load_strategy = "eager"
    if args.browser_binary:
        options.binary_location = str(Path(args.browser_binary).expanduser())

    if args.debugger_address:
        options.debugger_address = args.debugger_address
    else:
        profile_dir = Path(args.profile_dir).expanduser().resolve()
        profile_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_dir}")
        options.add_argument("--start-maximized")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-background-timer-throttling")
        options.add_argument("--disable-backgrounding-occluded-windows")
        options.add_argument("--disable-renderer-backgrounding")
        if args.language:
            options.add_argument(f"--lang={args.language}")

    try:
        return webdriver.Chrome(options=options)
    except WebDriverException as exc:
        raise CleanerError(
            "Không khởi động được Chrome WebDriver. Hãy cập nhật Google Chrome và Selenium, "
            "hoặc dùng --browser-binary để chỉ đúng file Chrome/Chromium."
        ) from exc


def _video_tile_count(driver: WebDriver) -> int:
    return int(driver.execute_script(VIDEO_TILE_COUNT_JS) or 0)


def _open_video_gallery_from_navigation(driver: WebDriver, timeout_seconds: float = 15) -> bool:
    """Use Google Photos' current Video navigation URL instead of a stale hard-coded route."""
    if _video_tile_count(driver) > 0:
        return True

    nav_element = driver.execute_script(FIND_VIDEO_NAV_ELEMENT_JS)
    if nav_element is None:
        return False
    nav_url = str(nav_element.get_attribute("href") or "")
    parsed = urlparse(nav_url)
    if parsed.hostname != "photos.google.com" or not parsed.path.lower().startswith("/search/"):
        return False

    LOGGER.info("Mở mục Video bằng liên kết điều hướng hiện tại của Google Photos.")
    driver.execute_script("arguments[0].click();", nav_element)
    try:
        WebDriverWait(driver, timeout_seconds, poll_frequency=0.25).until(
            lambda current_driver: _video_tile_count(current_driver) > 0
        )
    except TimeoutException:
        LOGGER.warning("Mục Video đã mở nhưng chưa thấy tile nào sau %.0f giây.", timeout_seconds)
        return False
    return True


def prompt_ready(
    driver: WebDriver,
    start_url: str,
    no_ready_prompt: bool,
    *,
    attached: bool,
) -> None:
    if not start_url.startswith("https://photos.google.com/"):
        raise CleanerError("--start-url phải thuộc https://photos.google.com/")

    # An attached Chrome was opened and authenticated by the user. Preserve its
    # current page; forcing an old search URL here can replace a working gallery
    # with an empty search route.
    if not attached:
        driver.get(start_url)
    if no_ready_prompt:
        _open_video_gallery_from_navigation(driver)
        return
    print(
        "\nChrome đã mở. Thực hiện trong cửa sổ đó:\n"
        "  1. Đăng nhập Google thủ công nếu được yêu cầu.\n"
        "  2. Mở Google Photos > Tìm kiếm > Video (nếu URL mở sẵn không đúng).\n"
        "  3. Bỏ chọn mọi ảnh/video đang được chọn.\n"
        "  4. Không mở Thùng rác hoặc một album chia sẻ.\n"
    )
    input("Khi lưới Video đã hiển thị, nhấn Enter tại đây để bắt đầu dry-run... ")
    _open_video_gallery_from_navigation(driver)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Quét Google Photos bằng Selenium và tuỳ chọn chuyển các video có nhãn thời lượng "
            "ngắn hơn ngưỡng vào Thùng rác. Mặc định chỉ dry-run."
        )
    )
    parser.add_argument("--threshold", type=float, default=4.0, help="Ngưỡng giây, so sánh nghiêm ngặt < (mặc định: 4).")
    parser.add_argument("--delete", action="store_true", help="Sau dry-run, cho phép chuyển mục khớp vào Thùng rác.")
    parser.add_argument("--confirm", default="", help=f"Xác nhận không tương tác: phải đúng {CONFIRM_PHRASE}.")
    parser.add_argument("--batch-size", type=int, default=25, help="Số video tối đa mỗi lô xoá (mặc định: 25, tối đa: 100).")
    parser.add_argument("--limit", type=int, default=0, help="Giới hạn tổng số video chuyển vào Thùng rác; 0 = theo toàn bộ dry-run.")
    parser.add_argument("--profile-dir", default=str(Path.home() / ".gphotos-short-video-cleaner" / "chrome-profile"))
    parser.add_argument("--debugger-address", default="", help="Gắn vào Chrome đã chạy remote debugging, ví dụ 127.0.0.1:9222.")
    parser.add_argument("--browser-binary", default="", help="Đường dẫn Chrome/Chromium nếu Selenium không tự tìm thấy.")
    parser.add_argument("--language", default="", help="Ngôn ngữ Chrome, ví dụ vi-VN; để trống để giữ mặc định.")
    parser.add_argument("--start-url", default=DEFAULT_START_URL)
    parser.add_argument("--output-dir", default="reports")
    parser.add_argument("--max-scrolls", type=int, default=10000)
    parser.add_argument("--scroll-settle", type=float, default=0.45, help="Thời gian chờ lazy-load sau mỗi lần cuộn.")
    parser.add_argument("--action-timeout", type=float, default=15.0)
    parser.add_argument("--no-ready-prompt", action="store_true", help="Không chờ Enter trước khi quét; chỉ dùng khi đã gắn Chrome sẵn.")
    parser.add_argument("--close-browser", action="store_true", help="Đóng Chrome ngay khi xong thay vì chờ Enter.")
    parser.add_argument("--log-level", choices=["DEBUG", "INFO", "WARNING", "ERROR"], default="INFO")
    args = parser.parse_args(argv)

    if args.threshold <= 0:
        parser.error("--threshold phải > 0")
    if not 1 <= args.batch_size <= 100:
        parser.error("--batch-size phải trong khoảng 1..100")
    if args.limit < 0:
        parser.error("--limit không được âm")
    if args.max_scrolls < 1:
        parser.error("--max-scrolls phải >= 1")
    if args.scroll_settle < 0.1:
        parser.error("--scroll-settle phải >= 0.1")
    if args.action_timeout < 2:
        parser.error("--action-timeout phải >= 2")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s | %(levelname)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    config = RuntimeConfig(
        threshold_seconds=args.threshold,
        batch_size=args.batch_size,
        limit=args.limit,
        max_scrolls=args.max_scrolls,
        scroll_settle_seconds=args.scroll_settle,
        action_timeout_seconds=args.action_timeout,
    )
    output_dir = Path(args.output_dir).expanduser().resolve()

    driver: WebDriver | None = None
    attached = bool(args.debugger_address)
    try:
        driver = build_driver(args)
        prompt_ready(driver, args.start_url, args.no_ready_prompt, attached=attached)
        assert_safe_page_context(driver)

        scan = scan_gallery(driver, config)
        scan.candidates = _dedupe_items(scan.candidates)
        scan.all_videos = _dedupe_items(scan.all_videos)
        scan.videos_without_duration = _dedupe_items(scan.videos_without_duration)
        scan_csv, scan_json = write_scan_reports(scan, output_dir)

        print("\n=== KẾT QUẢ DRY-RUN ===")
        print(f"Video nhận diện trong phiên quét: {len(scan.all_videos)}")
        print(f"Video có thời lượng hiển thị < {config.threshold_seconds:g} giây: {len(scan.candidates)}")
        print(f"Video không đọc được badge thời lượng (đã bỏ qua): {len(scan.videos_without_duration)}")
        print(f"CSV:  {scan_csv}")
        print(f"JSON: {scan_json}")
        print(
            "Lưu ý: tool dùng số giây hiển thị trên thumbnail. Với ngưỡng 4, chỉ badge 0:00–0:03 được nhận."
        )

        if not args.delete or not scan.candidates:
            return 0

        # A label alone can collide across multiple tiles. Such rows stay in the
        # report but are excluded from destructive mode.
        delete_plan = [item for item in scan.candidates if item.key_source != "aria-label"]
        weak_identity_count = len(scan.candidates) - len(delete_plan)
        if weak_identity_count:
            print(
                f"Bỏ qua {weak_identity_count} ứng viên khi xoá vì tile chỉ có aria-label, "
                "không có định danh đủ mạnh."
            )
        if not delete_plan:
            print("Không còn ứng viên có định danh đủ mạnh để xoá; chỉ giữ kết quả dry-run.")
            return 0

        planned = len(delete_plan)
        if config.limit > 0:
            planned = min(planned, config.limit)
        confirmation = args.confirm.strip()
        if confirmation != CONFIRM_PHRASE:
            print(
                f"\nSắp chuyển tối đa {planned} video vào Thùng rác. "
                "Thao tác có thể đồng bộ sang thiết bị đang bật sao lưu."
            )
            confirmation = input(f"Nhập chính xác {CONFIRM_PHRASE} để tiếp tục: ").strip()
        if confirmation != CONFIRM_PHRASE:
            print("Không xác nhận; chỉ giữ kết quả dry-run.")
            return 0

        result = delete_candidates(driver, config, delete_plan)
        delete_report = write_delete_report(result, output_dir)
        print("\n=== KẾT QUẢ XOÁ ===")
        print(f"Đã chuyển vào Thùng rác: {len(result.deleted)}/{result.planned}")
        print(f"Lý do dừng: {result.stopped_reason}")
        print(f"Báo cáo: {delete_report}")
        if result.failed_clicks:
            failed_total = sum(1 for count in result.failed_clicks.values() if count >= 3)
            print(f"Tile bị bỏ qua sau 3 lần chọn thất bại: {failed_total}")
        return 0

    except KeyboardInterrupt:
        print("\nĐã dừng bởi người dùng. Những mục chưa xác nhận xoá vẫn được giữ nguyên.")
        return 130
    except SafetyStop as exc:
        LOGGER.error("DỪNG AN TOÀN: %s", exc)
        return 2
    except CleanerError as exc:
        LOGGER.error("%s", exc)
        return 1
    except Exception as exc:  # pragma: no cover - preserve diagnostics for UI drift
        LOGGER.exception("Lỗi không dự kiến: %s", exc)
        return 1
    finally:
        if driver is not None:
            if not args.close_browser and sys.stdin.isatty():
                try:
                    input("\nNhấn Enter để kết thúc phiên Selenium...")
                except (EOFError, KeyboardInterrupt):
                    pass
            if not attached:
                try:
                    driver.quit()
                except WebDriverException:
                    pass


if __name__ == "__main__":
    raise SystemExit(main())
