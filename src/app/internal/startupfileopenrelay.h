/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2026 MuseScore Limited and others
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
#pragma once

#include <optional>

#include <QCoreApplication>
#include <QFileOpenEvent>
#include <QObject>
#include <QUrl>

namespace mu::app {
// macOS can deliver the document passed by Finder before the app-shell
// controller has installed its event filter. Buffer that first startup event
// while the application is being constructed, then hand it to the startup
// scenario before the first window is opened.
class StartupFileOpenRelay final : public QObject
{
public:
    static std::optional<QUrl> pendingUrl()
    {
        return s_accepting ? s_pendingUrl : std::nullopt;
    }

    static std::optional<QUrl> takePendingUrl()
    {
        if (!s_accepting) {
            return std::nullopt;
        }

        std::optional<QUrl> result = std::move(s_pendingUrl);
        s_pendingUrl.reset();
        s_accepting = false;
        return result;
    }

private:
    bool eventFilter(QObject* watched, QEvent* event) override
    {
        if (s_accepting && watched == qApp && event->type() == QEvent::FileOpen) {
            const QFileOpenEvent* fileOpenEvent = static_cast<const QFileOpenEvent*>(event);
            const QUrl url = fileOpenEvent->url();
            if (url.isValid() && !s_pendingUrl.has_value()) {
                s_pendingUrl = url;
            }
        }

        return false;
    }

    inline static bool s_accepting = true;
    inline static std::optional<QUrl> s_pendingUrl;
};
}
