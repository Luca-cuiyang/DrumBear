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

#include "templatesmodel.h"

#include "log.h"

using namespace mu::project;
using namespace muse;

namespace mu::project {
inline bool operator==(const Template& templ1, const Template& templ2)
{
    return templ1.meta.filePath == templ2.meta.filePath;
}
}

TemplatesModel::TemplatesModel(QObject* parent)
    : QObject(parent), muse::Contextable(muse::iocCtxForQmlObject(this))
{
}

void TemplatesModel::load()
{
    TRACEFUNC;

    RetVal<Templates> templates = repository()->templates();
    if (!templates.ret) {
        LOGE() << templates.ret.toString();
    }

    for (const Template& templ : templates.val) {
        if (!templ.meta.title.isEmpty()) {
            m_allTemplates << templ;
        }
    }

    loadAllCategories();
}

void TemplatesModel::loadAllCategories()
{
    TRACEFUNC;

    QStringList visibleCategories;

    for (const Template& templ: m_allTemplates) {
        if (!visibleCategories.contains(templ.categoryTitle)) {
            visibleCategories << templ.categoryTitle;
        }
    }

    setVisibleCategories(visibleCategories);
    updateTemplatesByCurrentCategory();
}

static QString zhTemplateTitle(const QString& english)
{
    static const QHash<QString, QString> zh = {
        { "General", "通用" }, { "Choral", "合唱" }, { "Chamber Music", "室内乐" },
        { "Solo", "独奏" }, { "Jazz", "爵士" }, { "Popular", "流行" },
        { "Band and Percussion", "管乐队与打击乐" }, { "Orchestral", "管弦乐" },
        { "Treble Clef", "高音谱表" }, { "Bass Clef", "低音谱表" }, { "Grand Staff", "大谱表" },
        { "SATB", "混声四部合唱" }, { "SATB + Organ", "混声四部合唱 + 管风琴" },
        { "SATB + Piano", "混声四部合唱 + 钢琴" },
        { "SATB Closed Score", "混声四部合唱（紧缩谱）" },
        { "SATB Closed Score + Organ", "混声四部合唱（紧缩谱）+ 管风琴" },
        { "SATB Closed Score + Piano", "混声四部合唱（紧缩谱）+ 钢琴" },
        { "Voice + Piano", "独唱 + 钢琴" },
        { "Barbershop Ensemble (TTBB)", "男声四重唱（TTBB）" },
        { "Barbershop Ensemble (SSAA)", "女声四重唱（SSAA）" },
        { "Barbershop Ensemble (SATB)", "四重唱（SATB）" },
        { "Liturgical Unmetrical", "无节拍礼仪音乐" },
        { "Liturgical Unmetrical + Organ", "无节拍礼仪音乐 + 管风琴" },
        { "String Quartet", "弦乐四重奏" }, { "Wind Quartet", "木管四重奏" },
        { "Wind Quintet", "木管五重奏" }, { "Saxophone Quartet", "萨克斯四重奏" },
        { "Brass Quartet", "铜管四重奏" }, { "Brass Quintet", "铜管五重奏" },
        { "Guitar", "吉他" }, { "Guitar + Tablature", "吉他 + 六线谱" },
        { "Guitar Tablature", "吉他六线谱" }, { "Piano", "钢琴" },
        { "Jazz Lead Sheet", "爵士主旋律谱" }, { "Big Band", "大乐队" },
        { "Jazz Combo", "爵士小乐队" }, { "Rock Band", "摇滚乐队" },
        { "Bluegrass Band", "蓝草乐队" }, { "Concert Band", "管乐团" },
        { "Small Concert Band", "小型管乐团" }, { "Brass Band", "铜管乐团" },
        { "Marching Band", "行进管乐团" }, { "Small Marching Band", "小型行进管乐团" },
        { "Battery Percussion", "打击乐" }, { "Large Pit Percussion", "大型前排打击乐" },
        { "Small Pit Percussion", "小型前排打击乐" }, { "European Concert Band", "欧式管乐团" },
        { "Classical Orchestra", "古典管弦乐团" }, { "Symphony Orchestra", "交响乐团" },
        { "String Orchestra", "弦乐团" }, { "My First Score", "我的第一份乐谱" },
    };
    return zh.value(english, english);
}

QStringList TemplatesModel::categoriesTitles() const
{
    QStringList titles;
    for (const QString& title : m_visibleCategoriesTitles) {
        titles << zhTemplateTitle(title);
    }
    return titles;
}

int TemplatesModel::currentCategoryIndex() const
{
    return m_visibleCategoriesTitles.indexOf(m_currentCategory);
}

int TemplatesModel::currentTemplateIndex() const
{
    return m_visibleTemplates.indexOf(m_currentTemplate);
}

QString TemplatesModel::currentTemplatePath() const
{
    return m_currentTemplate.meta.filePath.toQString();
}

QStringList TemplatesModel::templatesTitles() const
{
    QStringList titles;

    for (const Template& templ: m_visibleTemplates) {
        QString titleToAdd = templ.isCustom ? templ.meta.fileName(false).toQString() : templ.meta.title;
        titles << zhTemplateTitle(titleToAdd);
    }

    return titles;
}

void TemplatesModel::setCurrentCategoryIndex(int index)
{
    setCurrentCategory(m_visibleCategoriesTitles.value(index));
    updateTemplatesByCurrentCategory();
}

void TemplatesModel::setVisibleTemplates(const Templates& templates)
{
    if (m_visibleTemplates == templates) {
        return;
    }

    m_visibleTemplates = templates;
    emit templatesChanged();

    setCurrentTemplate(templates.value(0));
}

void TemplatesModel::setCurrentTemplate(const Template& templ)
{
    if (m_currentTemplate == templ) {
        return;
    }

    m_currentTemplate = templ;
    emit currentTemplateChanged();
}

void TemplatesModel::setVisibleCategories(const QStringList& titles)
{
    if (m_visibleCategoriesTitles == titles) {
        return;
    }

    m_visibleCategoriesTitles = titles;
    emit categoriesChanged();

    if (m_saveCurrentCategory) {
        m_saveCurrentCategory = false;
        // when the visibleCategoriesTitles are updated, the UI currentCategoryIndex needs to be updated,
        // even if we want the currentCategory to remain the same. So we need to force an emit:
        emit currentCategoryChanged();
    } else {
        setCurrentCategory(titles.value(0));
    }
}

void TemplatesModel::setCurrentCategory(const QString& category)
{
    if (m_currentCategory == category) {
        return;
    }

    m_currentCategory = category;
    emit currentCategoryChanged();
}

void TemplatesModel::updateTemplatesByCurrentCategory()
{
    TRACEFUNC;

    QStringList titles = categoriesTitles();
    if (titles.isEmpty()) {
        return;
    }

    Templates newVisibleTemplates;

    for (const Template& templ: m_allTemplates) {
        if (templ.categoryTitle == m_currentCategory) {
            newVisibleTemplates << templ;
        }
    }

    setVisibleTemplates(newVisibleTemplates);
}

void TemplatesModel::setCurrentTemplateIndex(int index)
{
    setCurrentTemplate(m_visibleTemplates.value(index));

    if (isSearching()) {
        setCurrentCategory(m_currentTemplate.categoryTitle);
    }
}

void TemplatesModel::saveCurrentCategory()
{
    m_saveCurrentCategory = true;
}

void TemplatesModel::setSearchText(const QString& text)
{
    if (m_searchText == text) {
        return;
    }

    m_searchText = text;
    updateTemplatesAndCategoriesBySearch();
}

void TemplatesModel::updateTemplatesAndCategoriesBySearch()
{
    TRACEFUNC;

    if (!isSearching()) {
        loadAllCategories();
        return;
    }

    QStringList newVisibleCategories;
    Templates newVisibleTemplates;

    for (const Template& templ: m_allTemplates) {
        if (titleAccepted(templ.meta.title) || titleAccepted(templ.categoryTitle)) {
            newVisibleTemplates << templ;

            if (!newVisibleCategories.contains(templ.categoryTitle)) {
                newVisibleCategories << templ.categoryTitle;
            }
        }
    }

    setVisibleCategories(newVisibleCategories);
    setVisibleTemplates(newVisibleTemplates);

    setCurrentCategory(m_currentTemplate.categoryTitle);
}

bool TemplatesModel::titleAccepted(const QString& title) const
{
    if (isSearching()) {
        return title.contains(m_searchText, Qt::CaseInsensitive);
    }

    return true;
}

bool TemplatesModel::isSearching() const
{
    return !m_searchText.isEmpty();
}
