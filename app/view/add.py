from flask import render_template, flash, redirect
from app import app, db
from app.user import reporter_required
from app.form import CVEForm, GroupForm
from app.model import CVE, CVEGroup, CVEGroupEntry, CVEGroupPackage
from app.model.enum import Remote, Status, Severity, Affected, affected_to_status, highest_severity
from app.util import multiline_to_list


ERROR_GROUP_WITH_ISSUE_EXISTS = 'The group AVG-{} already contains {} for the package {}'
ERROR_OPEN_GROUP_EXISTS = 'The group AVG-{} already has open issues for the package {}'


@app.route('/cve/add', methods=['GET', 'POST'])
@reporter_required
def add_cve():
    form = CVEForm()
    if not form.validate_on_submit():
        return render_template('form/cve.html',
                               title='Add CVE',
                               form=form,
                               CVE=CVE)

    cve = db.get(CVE, id=form.cve.data)
    if cve is not None:
        flash('{} already existed, redirected to edit form:'.format(cve.id))
        return redirect('/{}/edit'.format(cve.id))

    cve = db.create(CVE, id=form.cve.data)
    cve.issue_type = form.issue_type.data
    cve.description = form.description.data
    cve.severity = Severity.fromstring(form.severity.data)
    cve.remote = Remote.fromstring(form.remote.data)
    cve.reference = form.reference.data
    cve.notes = form.notes.data
    db.session.commit()
    flash('Added {}'.format(cve.id))
    return redirect('/{}'.format(cve.id))


@app.route('/avg/add', methods=['GET', 'POST'])
@reporter_required
def add_group():
    form = GroupForm()
    if not form.validate_on_submit():
        return render_template('form/group.html',
                               title='Add AVG',
                               form=form,
                               CVEGroup=CVEGroup)

    issue_ids = multiline_to_list(form.cve.data)
    issue_ids = set(filter(lambda s: s.startswith('CVE-'), issue_ids))

    existing_issues = CVE.query.filter(CVE.id.in_(issue_ids)).all()
    existing_issue_ids = [issue.id for issue in existing_issues]

    pkgnames = multiline_to_list(form.pkgnames.data)

    # check if a package with a CVE clashes with an existing group
    if not form.force_submit.data:
        same_group = (db.session.query(CVEGroup, CVE, CVEGroupPackage)
                      .join(CVEGroupEntry).join(CVE).join(CVEGroupPackage)
                      .filter(CVEGroupPackage.pkgname.in_(pkgnames)))
        if issue_ids:
            same_group = same_group.filter(CVE.id.in_(issue_ids))
        same_group = same_group.all()
        if same_group:
            for group, cve, package in same_group:
                flash(ERROR_GROUP_WITH_ISSUE_EXISTS
                      .format(group.id, cve.id, package.pkgname), 'warning')
            return render_template('form/group.html',
                                   title='Add AVG',
                                   form=form,
                                   CVEGroup=CVEGroup,
                                   show_force=True)

    for cve_id in list(filter(lambda issue: issue not in existing_issue_ids, issue_ids)):
        cve = db.create(CVE, id=cve_id)
        existing_issues.append(cve)
        flash('Added {}'.format(cve.id))

    fixed = form.fixed.data
    affected = Affected.fromstring(form.status.data)
    status = affected_to_status(affected, pkgnames[0], fixed)
    severity = highest_severity([issue.severity for issue in existing_issues])
    advisory_qualified = form.advisory_qualified.data and status is not Status.not_affected

    group = db.create(CVEGroup,
                      affected=form.affected.data,
                      status=status,
                      fixed=fixed,
                      bug_ticket=form.bug_ticket.data,
                      reference=form.reference.data,
                      notes=form.notes.data,
                      severity=severity,
                      advisory_qualified=advisory_qualified)
    db.session.commit()

    for cve in existing_issues:
        db.create(CVEGroupEntry, group=group, cve=cve)

    for pkgname in pkgnames:
        db.get_or_create(CVEGroupPackage, pkgname=pkgname, group=group)
        flash('Added {}'.format(pkgname))

    db.session.commit()
    flash('Added {}'.format(group.name))
    return redirect('/{}'.format(group.name))
