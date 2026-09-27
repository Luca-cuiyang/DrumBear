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

#include <QString>

#include "global/types/uri.h"

namespace mu::project {
inline const muse::Uri NOTATION_PAGE_URI("dbscore://notation");
inline const muse::Uri NOTATION_REVIEW_PAGE_URI("dbscore://notation/review");
inline const muse::Uri HOME_PAGE_URI("dbscore://home");
inline const muse::Uri NEW_SCORE_URI("dbscore://project/newscore");
inline const muse::Uri PROJECT_PROPERTIES_URI("dbscore://project/properties");
inline const muse::Uri UPLOAD_PROGRESS_URI("dbscore://project/upload/progress");

inline const QString DBSCORE_URL_SCHEME("dbscore");
inline const QString OPEN_SCORE_URL_HOSTNAME("open-score");
}
