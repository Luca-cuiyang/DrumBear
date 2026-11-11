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
#include "recentscoresmodel.h"

#include <QDir>
#include <QStandardPaths>

#include "translation.h"
#include "dataformatter.h"
#include "io/fileinfo.h"

#include "engraving/infrastructure/mscio.h"

#include "log.h"

using namespace muse;
using namespace mu::project;

namespace {
bool isProtectedUserLocation(const muse::io::path_t& path)
{
#if defined(Q_OS_MACOS) || defined(Q_OS_MAC)
    const QString candidate = QDir::cleanPath(path.toQString());
    const QList<QStandardPaths::StandardLocation> locations {
        QStandardPaths::DesktopLocation,
        QStandardPaths::DocumentsLocation,
        QStandardPaths::DownloadLocation
    };
    for (const QStandardPaths::StandardLocation location : locations) {
        const QString root = QDir::cleanPath(QStandardPaths::writableLocation(location));
        if (!root.isEmpty()
                && (candidate == root || candidate.startsWith(root + QLatin1Char('/')))) {
            return true;
        }
    }
#else
    (void)path;
#endif
    return false;
}
}

RecentScoresModel::RecentScoresModel(QObject* parent)
    : AbstractScoresModel(parent), muse::Contextable(muse::iocCtxForQmlObject(this))
{
}

void RecentScoresModel::load()
{
    updateRecentScores();

    recentFilesController()->recentFilesListChanged().onNotify(this, [this]() {
        updateRecentScores();
    });
}

void RecentScoresModel::removeRecentScore(const QString& scorePath)
{
    recentFilesController()->removeRecentFile(scorePath);
}

void RecentScoresModel::setRecentScores(const std::vector<QVariantMap>& items)
{
    if (m_items == items) {
        return;
    }

    beginResetModel();
    m_items = items;
    endResetModel();
}

void RecentScoresModel::updateRecentScores()
{
    const RecentFilesList& recentScores = recentFilesController()->recentFilesList();

    std::vector<QVariantMap> items;
    items.reserve(recentScores.size() + 2);

    QVariantMap addItem;
    addItem[NAME_KEY] = muse::qtrc("project", "新建乐谱");
    addItem[IS_CREATE_NEW_KEY] = true;
    addItem[IS_NO_RESULTS_FOUND_KEY] = false;
    items.push_back(addItem);

    for (const RecentFile& file : recentScores) {
        if (configuration()->isCloudProject(file.path)
                || isProtectedUserLocation(file.path)) {
            continue;
        }

        QVariantMap obj;

        std::string suffix = io::suffix(file.path);
        bool isSuffixInteresting = suffix != engraving::MSCZ;

        RetVal<uint64_t> fileSize = fileSystem()->fileSize(file.path);
        QString fileSizeString = (fileSize.ret && fileSize.val > 0) ? DataFormatter::formatFileSize(fileSize.val).toQString() : QString();

        obj[NAME_KEY] = file.displayName(isSuffixInteresting);
        obj[PATH_KEY] = file.path.toQString();
        obj[SUFFIX_KEY] = QString::fromStdString(suffix);
        obj[FILE_SIZE_KEY] = fileSizeString;
        obj[TIME_SINCE_MODIFIED_KEY] = DataFormatter::formatTimeSince(io::FileInfo(file.path).lastModified().date()).toQString();
        obj[IS_CREATE_NEW_KEY] = false;
        obj[IS_NO_RESULTS_FOUND_KEY] = false;

        items.push_back(obj);
    }

    QVariantMap noResultsFoundItem;
    noResultsFoundItem[NAME_KEY] = "";
    noResultsFoundItem[IS_CREATE_NEW_KEY] = false;
    noResultsFoundItem[IS_NO_RESULTS_FOUND_KEY] = true;
    items.push_back(noResultsFoundItem);

    setRecentScores(items);
}

QList<int> RecentScoresModel::nonScoreItemIndices() const
{
    return { 0, rowCount() - 1 };
}
