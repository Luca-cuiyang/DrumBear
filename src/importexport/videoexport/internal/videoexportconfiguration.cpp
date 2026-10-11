/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2021 MuseScore Limited and others
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU General Public License version 3 as
 * published by the Free Software Foundation.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU General Public License for more details.
 *
 * You should have received a copy of the GNU General Public License
 * along with this program.  If not, see <https://www.gnu.org/licenses/>.
 */
#include "videoexportconfiguration.h"

using namespace mu::iex::videoexport;

static const ViewMode DEFAULT_VIEW_MODE = ViewMode::PageFull;
static const bool DEFAULT_SHOW_PIANO = false;
static const PianoPosition DEFAULT_PIANO_POSITION = PianoPosition::Bottom;
static const std::string DEFAULT_RESOLUTION = "4k_16x9";
static const int DEFAULT_CUSTOM_WIDTH = 1920;
static const int DEFAULT_CUSTOM_HEIGHT = 1080;
static const int DEFAULT_FPS = 24;
static const double DEFAULT_LEADING_SEC = 3.0;
static const double DEFAULT_TRAILING_SECONDS = 3.0;
static const bool DEFAULT_SMOOTH_PAGE_TRANSITIONS = false;

static const std::vector<std::string> AVAILABLE_RESOLUTIONS = { "4k_16x9", "4k_9x16", "custom" };

ViewMode VideoExportConfiguration::viewMode() const
{
    return m_viewMode ? m_viewMode.value() : DEFAULT_VIEW_MODE;
}

void VideoExportConfiguration::setViewMode(std::optional<ViewMode> viewMode)
{
    m_viewMode = viewMode;
}

bool VideoExportConfiguration::showPiano() const
{
    return m_showPiano ? m_showPiano.value() : DEFAULT_SHOW_PIANO;
}

void VideoExportConfiguration::setShowPiano(std::optional<bool> showPiano)
{
    m_showPiano = showPiano;
}

PianoPosition VideoExportConfiguration::pianoPosition() const
{
    return m_pianoPosition ? m_pianoPosition.value() : DEFAULT_PIANO_POSITION;
}

void VideoExportConfiguration::setPianoPosition(std::optional<PianoPosition> position)
{
    m_pianoPosition = position;
}

std::string VideoExportConfiguration::resolution() const
{
    return m_resolution ? m_resolution.value() : DEFAULT_RESOLUTION;
}

void VideoExportConfiguration::setResolution(std::optional<std::string> resolution)
{
    m_resolution = resolution;
}

const std::vector<std::string>& VideoExportConfiguration::availableResolutions() const
{
    return AVAILABLE_RESOLUTIONS;
}

int VideoExportConfiguration::customWidth() const
{
    return m_customWidth ? m_customWidth.value() : DEFAULT_CUSTOM_WIDTH;
}

void VideoExportConfiguration::setCustomWidth(std::optional<int> width)
{
    m_customWidth = width;
}

int VideoExportConfiguration::customHeight() const
{
    return m_customHeight ? m_customHeight.value() : DEFAULT_CUSTOM_HEIGHT;
}

void VideoExportConfiguration::setCustomHeight(std::optional<int> height)
{
    m_customHeight = height;
}

int VideoExportConfiguration::fps() const
{
    return m_fps ? m_fps.value() : DEFAULT_FPS;
}

void VideoExportConfiguration::setFps(std::optional<int> fps)
{
    m_fps = fps;
}

double VideoExportConfiguration::leadingSec() const
{
    return m_leadingSec ? m_leadingSec.value() : DEFAULT_LEADING_SEC;
}

void VideoExportConfiguration::setLeadingSec(std::optional<double> leadingSec)
{
    m_leadingSec = leadingSec;
}

double VideoExportConfiguration::trailingSec() const
{
    return m_trailingSec ? m_trailingSec.value() : DEFAULT_TRAILING_SECONDS;
}

void VideoExportConfiguration::setTrailingSec(std::optional<double> trailingSec)
{
    m_trailingSec = trailingSec;
}

bool VideoExportConfiguration::smoothPageTransitions() const
{
    return m_smoothPageTransitions ? m_smoothPageTransitions.value() : DEFAULT_SMOOTH_PAGE_TRANSITIONS;
}

void VideoExportConfiguration::setSmoothPageTransitions(std::optional<bool> value)
{
    m_smoothPageTransitions = value;
}
