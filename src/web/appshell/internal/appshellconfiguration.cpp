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
#include "appshellconfiguration.h"

using namespace muse;
using namespace mu::appshell;

static const std::string module_name("appshell");

static bool s_notationNavigatorVisible = false;
static muse::async::Notification s_notationNavigatorVisibleChanged;

void AppShellConfiguration::init()
{
}

std::string AppShellConfiguration::museScoreVersion() const
{
    return String(application()->version().toString() + u"." + application()->build()).toStdString();
}

std::string AppShellConfiguration::museScoreRevision() const
{
    return application()->revision().toStdString();
}

bool AppShellConfiguration::isNotationNavigatorVisible() const
{
    return s_notationNavigatorVisible;
}

void AppShellConfiguration::setIsNotationNavigatorVisible(bool visible) const
{
    if (s_notationNavigatorVisible == visible) {
        return;
    }
    s_notationNavigatorVisible = visible;
    s_notationNavigatorVisibleChanged.notify();
}

muse::async::Notification AppShellConfiguration::isNotationNavigatorVisibleChanged() const
{
    return s_notationNavigatorVisibleChanged;
}
