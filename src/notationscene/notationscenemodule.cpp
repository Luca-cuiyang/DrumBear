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
#include "notationscenemodule.h"

#include "modularity/ioc.h"
#include "interactive/iinteractiveuriregister.h"
#include "ui/iuiactionsregister.h"
#include "rcommand/icommandsregister.h"
#include "rcommand/icommandsstate.h"

#include "internal/notationsceneconfiguration.h"
#include "internal/notationactioncontroller.h"
#include "internal/midiinputoutputcontroller.h"
#include "internal/notationuiactions.h"
#include "internal/notationactionsshortcutsmigrator.h"
#include "internal/notationcommandsregister.h"
#include "internal/notationcommandsstate.h"
#include "internal/notationactioncontroller.h"

#include "widgets/breaksdialog.h"
#include "widgets/editstaff.h"
#include "widgets/editstringdata.h"
#include "widgets/editstyle.h"
#include "widgets/measureproperties.h"
#include "widgets/pagesettings.h"
#include "widgets/realizeharmonydialog.h"
#include "widgets/selectdialog.h"
#include "widgets/selectnotedialog.h"
#include "widgets/stafftextpropertiesdialog.h"
#include "widgets/transposedialog.h"
#include "widgets/tupletdialog.h"

using namespace mu::notation;
using namespace muse;
using namespace muse::modularity;

static const std::string mname("notationscene");

std::string NotationSceneModule::moduleName() const
{
    return mname;
}

void NotationSceneModule::registerExports()
{
    m_configuration = std::make_shared<NotationSceneConfiguration>();

    globalIoc()->registerExport<INotationSceneConfiguration>(mname, m_configuration);
}

void NotationSceneModule::resolveImports()
{
    auto ir = globalIoc()->resolve<muse::interactive::IInteractiveUriRegister>("notationscene");
    if (ir) {
        ir->registerWidgetUri<EditStyle>(Uri("dbscore://notation/style"));
        ir->registerWidgetUri<PageSettings>(Uri("dbscore://notation/pagesettings"));
        ir->registerWidgetUri<MeasurePropertiesDialog>(Uri("dbscore://notation/measureproperties"));
        ir->registerWidgetUri<BreaksDialog>(Uri("dbscore://notation/breaks"));
        ir->registerWidgetUri<EditStaff>(Uri("dbscore://notation/staffproperties"));
        ir->registerWidgetUri<EditStringData>(Uri("dbscore://notation/editstrings"));
        ir->registerWidgetUri<TransposeDialog>(Uri("dbscore://notation/transpose"));
        ir->registerWidgetUri<SelectNoteDialog>(Uri("dbscore://notation/selectnote"));
        ir->registerWidgetUri<SelectDialog>(Uri("dbscore://notation/selectelement"));
        ir->registerWidgetUri<TupletDialog>(Uri("dbscore://notation/othertupletdialog"));
        ir->registerWidgetUri<StaffTextPropertiesDialog>(Uri("dbscore://notation/stafftextproperties"));
        ir->registerWidgetUri<RealizeHarmonyDialog>(Uri("dbscore://notation/realizechordsymbols"));

        ir->registerQmlUri(Uri("dbscore://notation/parts"), "DBScore.NotationScene", "PartsDialog");
        ir->registerQmlUri(Uri("dbscore://notation/selectmeasurescount"), "DBScore.NotationScene", "SelectMeasuresCountDialog");
        ir->registerQmlUri(Uri("dbscore://notation/editgridsize"), "DBScore.NotationScene", "EditGridSizeDialog");
        ir->registerQmlUri(Uri("dbscore://notation/percussionpanelpadswap"), "DBScore.NotationScene", "PercussionPanelPadSwapDialog");
        ir->registerQmlUri(Uri("dbscore://notation/editpercussionshortcut"), "DBScore.NotationScene", "EditPercussionShortcutDialog");
    }

    auto cr = globalIoc()->resolve<muse::rcommand::ICommandsRegister>(mname);
    if (cr) {
        cr->reg(std::make_shared<NotationCommandsRegister>());
    }
}

void NotationSceneModule::onInit(const IApplication::RunMode&)
{
    m_configuration->init();
}

IContextSetup* NotationSceneModule::newContext(const muse::modularity::ContextPtr& ctx) const
{
    return new NotationSceneContext(ctx);
}

void NotationSceneContext::registerExports()
{
    m_actionController = std::make_shared<NotationActionController>(iocContext());
    m_notationUiActions = std::make_shared<NotationUiActions>(m_actionController, iocContext());
    m_midiInputOutputController = std::make_shared<MidiInputOutputController>(iocContext());

    ioc()->registerExport<INotationCommandsController>(mname, m_actionController);
}

void NotationSceneContext::resolveImports()
{
    auto ar = ioc()->resolve<muse::ui::IUiActionsRegister>("notationscene");
    if (ar) {
        ar->reg(m_notationUiActions);
    }

    auto cs = ioc()->resolve<muse::rcommand::ICommandsState>(mname);
    if (cs) {
        cs->reg(std::make_shared<NotationCommandsState>(iocContext()));
    }
}

void NotationSceneContext::onInit(const IApplication::RunMode& mode)
{
    m_actionController->init();
    m_notationUiActions->init();

    if (mode == IApplication::RunMode::GuiApp) {
        m_midiInputOutputController->init();
    }
}

void NotationSceneContext::onAllInited(const IApplication::RunMode& mode)
{
    if (mode == IApplication::RunMode::GuiApp) {
        NotationActionsShortcutsMigrator::migrate(iocContext());
    }
}
