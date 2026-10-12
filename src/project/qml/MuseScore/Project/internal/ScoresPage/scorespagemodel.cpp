/*
 * SPDX-License-Identifier: GPL-3.0-only
 * MuseScore-Studio-CLA-applies
 *
 * MuseScore Studio
 * Music Composition & Notation
 *
 * Copyright (C) 2023 MuseScore Limited and others
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

#include "scorespagemodel.h"

#include <QString>

#include "actions/actiontypes.h"
#include "log.h"

#include "engraving/dom/masterscore.h"
#include "engraving/dom/staff.h"
#include "engraving/dom/stafftype.h"
#include "engraving/types/fraction.h"
#include "notation/imasternotation.h"
#include "notation/inotationparts.h"
#include "project/iopenprojectscenario.h"
#include "types/projectcreateoptions.h"

using namespace mu::project;
using namespace muse::actions;

ScoresPageModel::ScoresPageModel(QObject* parent)
    : QObject(parent), muse::Contextable(muse::iocCtxForQmlObject(this))
{
}

void ScoresPageModel::createNewScore()
{
    dispatcher()->dispatch("file-new");
}

void ScoresPageModel::createJianpuScore()
{
    ProjectCreateOptions options;
    options.title = muse::qtrc("project", "简谱");

    notation::ScoreCreateOptions& scoreOptions = options.scoreOptions;
    scoreOptions.withTempo = false;
    scoreOptions.globalTimesig = engraving::Fraction(4, 4);
    scoreOptions.timesigType = engraving::TimeSigType::NORMAL;
    scoreOptions.key = engraving::Key::C;
    scoreOptions.totalMeasures = 32;

    notation::PartInstrument pi;
    pi.instrumentTemplate = instrumentsRepository()->instrumentTemplate(u"voice");
    pi.isExistingPart = false;
    pi.isSoloist = false;
    scoreOptions.parts << pi;

    auto project = notationCreator()->newProject(iocContext());
    muse::Ret ret = project->createNew(options);
    if (!ret) {
        LOGE() << ret.toString();
        return;
    }

    auto score = project->masterNotation()->masterScore();
    auto parts = project->masterNotation()->parts();
    for (engraving::staff_idx_t i = 0; i < score->nstaves(); ++i) {
        engraving::Staff* staff = score->staff(i);
        if (staff) {
            parts->setStaffType(staff->id(), engraving::StaffTypes::JIANPU);
        }
    }

    globalContext()->setCurrentProject(project);
    openProjectScenario()->finishOpening();
}

void ScoresPageModel::convertFileToScore()
{
    dispatcher()->dispatch("file-convert-to-score");
}

void ScoresPageModel::openOther()
{
    dispatcher()->dispatch("file-open");
}

void ScoresPageModel::openScore(const QString& scorePath, const QString& displayNameOverride)
{
    dispatcher()->dispatch("file-open", ActionData::make_arg2<QUrl, QString>(QUrl::fromLocalFile(scorePath), displayNameOverride));
}

void ScoresPageModel::revealInFileBrowser(const QString& scorePath)
{
    muse::Ret ret = platformInteractive()->revealInFileBrowser(scorePath);
    if (!ret) {
        LOGE() << ret.toString();
    }
}

ScoresPageModel::ViewType ScoresPageModel::viewType() const
{
    return static_cast<ViewType>(configuration()->homeScoresPageViewType());
}

void ScoresPageModel::setViewType(ViewType type)
{
    if (viewType() == type) {
        return;
    }

    configuration()->setHomeScoresPageViewType(IProjectConfiguration::HomeScoresPageViewType(type));
    emit viewTypeChanged();
}
