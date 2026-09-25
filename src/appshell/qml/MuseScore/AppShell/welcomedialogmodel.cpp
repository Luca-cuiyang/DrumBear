/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2025 MuseScore Limited and others
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

#include "welcomedialogmodel.h"

#include "translation.h"
#include "log.h"

using namespace mu::appshell;

static std::vector<QVariantMap> welcomeDialogData()
{
    QVariantMap welcome;
    welcome.insert("title", muse::qtrc("appshell/welcome", "Welcome to DB Score"));
    welcome.insert("imageUrl", "qrc:/resources/welcomedialog/WhatsNew.png");
    welcome.insert("description", muse::qtrc("appshell/welcome",
                                              "DB Score is a free, open source music notation software, forked from MuseScore Studio and licensed under GPL-3.0."));
    welcome.insert("buttonText", muse::qtrc("appshell/welcome", "Learn more"));
    welcome.insert("destinationUrl", "https://www.dbscore.app");

    QVariantMap create;
    create.insert("title", muse::qtrc("appshell/welcome", "Create, play and print"));
    create.insert("imageUrl", "qrc:/resources/welcomedialog/ExploreTutorials.png");
    create.insert("description", muse::qtrc("appshell/welcome",
                                            "Compose with an easy-to-use editor, hear your score in real time, and export to PDF, audio, MIDI and MusicXML."));
    create.insert("buttonText", muse::qtrc("appshell/welcome", "Open handbook"));
    create.insert("destinationUrl", "https://www.dbscore.app");

    QVariantMap openSource;
    openSource.insert("title", muse::qtrc("appshell/welcome", "Free and open source"));
    openSource.insert("imageUrl", "qrc:/resources/welcomedialog/WhatsNew.png");
    openSource.insert("description", muse::qtrc("appshell/welcome",
                                                 "DBScore respects your freedom: the full source code is available under the GNU GPL v3, so you can study, modify and share it."));
    openSource.insert("buttonText", muse::qtrc("appshell/welcome", "View source"));
    openSource.insert("destinationUrl", "https://github.com/dbscore/DBScore");

    //! NOTE: This is the order the above items will appear in the carousel
    return { welcome, create, openSource };
}

WelcomeDialogModel::WelcomeDialogModel()
    : muse::Contextable(muse::iocCtxForQmlObject(this))
{
}

void WelcomeDialogModel::init()
{
    IF_ASSERT_FAILED(configuration()) {
        return;
    }

    m_items = welcomeDialogData();

    m_currentIndex = configuration()->welcomeDialogLastShownIndex();
    nextItem();

    IF_ASSERT_FAILED(m_currentIndex != muse::nidx) {
        m_currentIndex = 0;
    }
    configuration()->setWelcomeDialogLastShownIndex(static_cast<int>(m_currentIndex));

    emit itemsChanged();
    emit currentItemChanged();
}

QVariantMap WelcomeDialogModel::currentItem() const
{
    if (m_items.empty()) {
        return QVariantMap();
    }
    return m_items.at(m_currentIndex);
}

void WelcomeDialogModel::nextItem()
{
    IF_ASSERT_FAILED(!m_items.empty()) {
        return;
    }

    if (hasNext()) {
        ++m_currentIndex;
    } else {
        // Cycle to first...
        m_currentIndex = 0;
    }
    configuration()->setWelcomeDialogLastShownIndex(static_cast<int>(m_currentIndex));

    emit currentItemChanged();
}

void WelcomeDialogModel::prevItem()
{
    IF_ASSERT_FAILED(!m_items.empty()) {
        return;
    }

    if (hasPrev()) {
        --m_currentIndex;
    } else {
        // Cycle to last....
        m_currentIndex = count() - 1;
    }
    configuration()->setWelcomeDialogLastShownIndex(static_cast<int>(m_currentIndex));

    emit currentItemChanged();
}

bool WelcomeDialogModel::showOnStartup() const
{
    return configuration()->welcomeDialogShowOnStartup();
}

void WelcomeDialogModel::setShowOnStartup(bool show)
{
    if (show == showOnStartup()) {
        return;
    }

    configuration()->setWelcomeDialogShowOnStartup(show);
    emit showOnStartupChanged();
}
