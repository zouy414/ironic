=========================
Releasing Ironic Projects
=========================

Since the responsibility for releases will move between people, we document
that process here.

A full list of projects that Ironic manages is available in the `governance
site`_.

.. _`governance site`: https://governance.openstack.org/reference/projects/ironic.html

Who is responsible for releases?
================================

The current PTL is ultimately responsible for making sure code gets released.
They may choose to delegate this responsibility to a liaison, which is
documented in the `cross-project liaison wiki`_.

Anyone may submit a release request per the process below, but the PTL or
liaison must +1 the request for it to be processed.

.. _`cross-project liaison wiki`: https://wiki.openstack.org/wiki/CrossProjectLiaisons#Release_management

Release process
===============

Releases are managed by the OpenStack release team. The release process is
documented in the `Project Team Guide`_.

.. _`Project Team Guide`: https://docs.openstack.org/project-team-guide/release-management.html#how-to-release

What do we have to release?
===========================

The Ironic project has a number of deliverables under its governance.  The
ultimate source of truth for this is `projects.yaml
<https://opendev.org/openstack/governance/src/branch/master/reference/projects.yaml>`__
in the governance repository. These deliverables have varying release models,
and these are defined in the `deliverables YAML files
<https://opendev.org/openstack/releases/src/branch/master/deliverables>`__ in
the releases repository.

In general, Ironic deliverables follow the `cycle-with-intermediary
<https://releases.openstack.org/reference/release_models.html#cycle-with-intermediary>`__
release model.

Non-client libraries
--------------------

The following deliverables are non-client libraries:

* ironic-lib
* metalsmith
* sushy

Client libraries
----------------

The following deliverables are client libraries:

* python-ironicclient
* python-ironic-inspector-client

Normal release
--------------

The following deliverables are Neutron plugins:

* networking-baremetal
* networking-generic-switch

The following deliverables are Horizon plugins:

* ironic-ui

The following deliverables are Tempest plugins:

* ironic-tempest-plugin

The following deliverables are tools:

* ironic-python-agent-builder

The following deliverables are services, or treated as such:

* bifrost
* ironic
* ironic-inspector
* ironic-prometheus-exporter
* ironic-python-agent

Manual release
--------------

The ironic-staging-drivers follows a different procedure, see
`Releasing ironic-staging-drivers
<https://ironic-staging-drivers.readthedocs.io/en/latest/releasing.html>`__.

Independent
-----------

The following deliverables are released `independently
<https://releases.openstack.org/reference/release_models.html#independent>`__:

* sushy-tools
* tenks
* virtualbmc

Not released
------------

The following deliverables do not need to be released:

* ironic-inspector-specs
* ironic-specs

Bugfix branches
===============

The following projects have ``bugfix/X.Y`` branches in addition to standard
openstack ``stable/NAME`` branches:

* ironic
* ironic-python-agent

These projects receive releases every six months as part of the coordinated
OpenStack release that happens semi-annually. These releases can be
found in a ``stable/NAME`` branch.

They are also evaluated for additional bugfix releases between scheduled
stable releases at the two and four month milestone between stable releases
(roughly every 2 months). These releases can be found in a ``bugfix/X.Y``
branch. A bugfix release is only created if there are significant
beneficial changes and a known downstream operator or distributor will consume
the release.

A bugfix branch is supported for 6 months after its creation date.

To leave some version space for releases from these branches, releases of these
projects from the master branch always increase either the major or the minor
version.

Currently retirement of bugfix branches cannot be automated and
must be done by the ironic team manually as explained below.

There are usually 3 bugfix branches present at all time, the latest 2 are
actively maintained, while the third one is considered unmaintained.
After creating a new bugfix branch, the oldest bugfix branch
should be tagged as EoL and deleted.

Only members of the ironic-core or ironic-release groups can delete branches,
please refer to this procedure to remove the oldest bugfix branch after
the creation of a new one:

* checkout locally the bugfix branch to move to EoL, if it does not exist
  locally it's possible to checkout it from remote and switch to it using
  ``git checkout -t``, for example for bugfix/24.0 use:

.. code-block:: bash

   git checkout -t origin/bugfix/24.0

* fast forward to latest change using:

.. code-block:: bash

   git pull --ff-only

* add a signed tag to the latest commit of the bugfix branch named ``bugfix-X.Y-eol``
  and add "EOL bugfix/X.Y" as description, for example
  for bugfix/24.0 add the tag bugfix-24.0-eol; use the ``git tag``
  command for that, for example for bugfix/24.0 the syntax would be:

.. code-block:: bash

   git tag -s bugfix-24.0-eol -m "EOL bugfix/24.0"

* push the new tag to gerrit using ``git push gerrit TAG_NAME``, for example
  for bugfix/24.0 use:

.. code-block:: bash

   git push gerrit bugfix-24.0-eol

* delete the bugfix branch on gerrit using ``git push gerrit --delete BUGFIX_BRANCH_NAME``,
  again for bugfix/24.0 would be:

.. code-block:: bash

   git push gerrit --delete bugfix/24.0

After the creation of a bugfix branch it is highly recommended to update
the upper-constraints link for the tests in the tox.ini file, plus override
the branch for the requirements project to be sure to use the correct
upper-constraints from the branch creation time; for example see the
following change:

https://review.opendev.org/c/openstack/ironic/+/938660

It is also mandatory to comment out or remove the metal3 integration job as it
is not supposed to run in stable or bugfix branches, and also comment out or
remove the tox codespell job to avoid failures due to version changes, spelling
is fixed in master and most recent stable branches only and backported "as is".

Things to do before releasing
=============================

* Review the unreleased release notes, if the project uses them. Make sure
  they follow our :ref:`standards <faq_release_note>`, are coherent, and have
  proper grammar.
  Combine release notes if necessary (for example, a release note for a
  feature and another release note to add to that feature may be combined).

* For Ironic releases only, not Ironic-inspector releases: if any new API
  microversions have been added since the last release, update the REST API
  version history (``doc/source/contributor/webapi-version-history.rst``) to
  indicate that they were part of the new release.

* To support rolling upgrades, add this new release version (and release name
  if it is a named release) into ``ironic/common/release_mappings.py``:

  * in ``RELEASE_MAPPING`` make a copy of the ``master`` entry, and rename the
    first ``master`` entry to the new semver release version.

  * If this is a named release, add a ``RELEASE_MAPPING`` entry for the named
    release. Its value should be the same as that of the latest semver one
    (that you just added above).

    It is important to do this before a stable/<release> branch is made (or if
    `the grenade switch is made <http://lists.openstack.org/pipermail/openstack-dev/2017-February/111849.html>`_
    to use the latest release from stable as the 'old' release).
    Otherwise, once it is made, CI (the grenade job that tests new-release ->
    master) will fail.

* Check for any open patches that are close to be merged or release critical.

  This usually includes important bug fixes and/or features that we'd like to
  release, including the related documentation.

How to propose a release
========================

The steps that lead to a release proposal are mainly manual, while proposing
the release itself is almost a 100% automated process, accomplished by
following the next steps:

* Clone the `openstack/releases <https://opendev.org/openstack/releases>`_
  repository. This is where deliverables are tracked and all the automation
  resides.

  * Under the ``deliverables`` directory you can see yaml files for each
    deliverable (i.e. subproject) grouped by release cycles.

  * The ``_independent`` directory contains yaml files for deliverables that
    are not bound to (official) cycles (e.g. Ironic-python-agent-builder).

* To check the changes we're about to release we can use the tox environment
  ``list-unreleased-changes``, with this syntax:

  .. code-block:: bash

    tox -e venv -- list-unreleased-changes <series> <deliverable>

  The ``series`` argument is a release series (i.e. master or train,
  not stable/ussuri or stable/train).

  For example, assuming we're in the main directory of the releases repository,
  to check the changes in the ussuri series for Ironic-python-agent
  type:

  .. code-block:: bash

    tox -e venv -- list-unreleased-changes ussuri openstack/ironic-python-agent

* To update the deliverable file for the new release, we use a scripted process
  in the form of a tox environment called ``new-release``.

  To get familiar with it and see all the options, type:

  .. code-block:: bash

    tox -e venv -- new-release -h

  Now, based on the list of changes we found in the precedent step, and the
  release notes, we need to decide on whether the next version will be major,
  minor (feature) or patch (bugfix).

  Note that in this case ``series`` is a code name (train, ussuri), not a
  branch. That is also valid for the current development branch (master) that
  takes the code name of the future stable release, for example if the future
  stable release code name is wallaby, we need to use wallaby as ``series``.

  The ``--stable-branch argument`` is used only for branching in the end of a
  cycle, independent projects are not branched this way though.

  The ``--intermediate-branch`` option is used to create an intermediate
  bugfix branch following the
  `new release model for Ironic projects <https://specs.openstack.org/openstack/ironic-specs/specs/approved/new-release-model.html>`_.

  To propose the release, use the script to update the deliverable file, then
  commit the change, and propose it for review.

  For example, to propose a minor release for Ironic in the master branch
  (current development branch), considering that the code name of the future
  stable release is wallaby, use:

  .. code-block:: bash

    tox -e venv -- new-release -v wallaby ironic feature

  Remember to use a meaningful topic, usually using the name of the
  deliverable, the new version and the branch, if applicable.

  A good commit message title should also include the same, for example
  "Release Ironic 1.2.3 for ussuri"

* As an optional step, we can use ``tox -e list-changes`` to double-check the
  changes before submitting them for review.

  Also ``tox -e validate`` (it might take a while to run based on the number of
  changes) does some some sanity-checks, but since everything is scripted,
  there shouldn't be any issue.

  All the scripts are designed and maintained by the release team; in case of
  questions or doubts or if any errors should arise, you can reach to them in
  the IRC channel ``#openstack-release``; all release liaisons should be
  present there.

* After the change is up for review, the PTL or a release liaison will have to approve
  it before it can get approved by the release team. Then, it will be processed
  automatically by zuul.

Things to do after releasing
============================

When a release is done that results in a stable branch
------------------------------------------------------
When a release is done that results in a stable branch for the project,
several changes need to be made.

The release automation will push a number of changes that need to be approved.
This includes:

* In the new stable branch:

  .. NOTE:: OpenStack Release tooling does this automatically.

  * a change to point ``.gitreview`` at the branch
  * a change to update the upper constraints file used by ``tox``

* In the master branch:

  * updating the release notes RST to include the new branch.

    The generated RST does not include the version range in the title, so we
    typically submit a follow-up patch to do that. An example of this patch is
    `here <https://review.opendev.org/685070>`__.

  * update the ``templates`` in ``.zuul.yaml`` or ``zuul.d/project.yaml``.

    The update is necessary to use the job for the next release
    ``openstack-python3-<next_release>-jobs``. An example of this patch is
    `here <https://review.opendev.org/#/c/689705/>`__.

We need to submit patches for changes in the stable branch to:

* update the Ironic devstack plugin to point at the branched tarball for IPA.
  An example of this patch is
  `here <https://review.opendev.org/685069/>`_.
* set appropriate defaults for ``TEMPEST_BAREMETAL_MIN_MICROVERSION`` and
  ``TEMPEST_BAREMETAL_MAX_MICROVERSION`` in ``devstack/lib/ironic`` to make sure
  that unsupported API tempest tests are skipped on stable branches. E.g.
  `patch 495319 <https://review.opendev.org/495319>`_.
* remove any CI jobs which are *not* required. Mainly this revolves around the
  metal3-integration CI job, however other non-voting jobs can also be removed
  safely. This can be achieved by editing the ``.zuul.d/project.yaml`` file.

.. NOTE:: It is normal to reduce the number of CI jobs present on a stable
   branch the longer the branch exists. This is a mix of challenges related
   to distributions, dependencies, and CI resources. Maintainers should
   anticipate this as a normal activity and should avoid heroic efforts.

We need to submit patches for changes on master to:

* to support rolling upgrades, since the release was a named release, we
  need to make these changes. Note that we need to wait until *after* the
  switch in grenade is made to test the latest release (N) with master
  (e.g. `for stable/queens <https://review.opendev.org/#/c/543615>`_).
  Doing these changes sooner -- after the Ironic release and before the switch
  when grenade is testing the prior release (N-1) with master, will cause
  the tests to fail. (You may want to ask/remind infra/qa team, as to
  when they will do this switch.)

  * In ``ironic/common/release_mappings.py``, delete any entries from
    ``RELEASE_MAPPING`` associated with the oldest named release. Since we
    support upgrades between adjacent named releases, the master branch will
    only support upgrades from the most recent named release to master.

  * remove any DB migration scripts from ``ironic.command.dbsync.ONLINE_MIGRATIONS``
    and remove the corresponding code from Ironic. (These migration scripts
    are used to migrate from an old release to this latest release; they
    shouldn't be needed after that.)

When a release is done that results in a bugfix branch
------------------------------------------------------

In this case the release management only creates a change to point
``.gitreview`` at the branch, ``tox.ini`` is not modified.

After the release:

* update the Tempest microversions as explained above.

* the CI needs additional configuration, so that Zuul knows which branch to
  take jobs definitions from. See the following examples:

  * `ironic 18.1 <https://review.opendev.org/c/openstack/ironic/+/801876>`_
  * `ironic-python-agent 8.1
    <https://review.opendev.org/c/openstack/ironic-python-agent/+/801898>`_

Ironic Tempest plugin
~~~~~~~~~~~~~~~~~~~~~

As **ironic-tempest-plugin** is branchless, we need to submit a patch adding
stable jobs to its master branch. `Example for Queens
<https://review.opendev.org/#/c/543555/>`_.

Bifrost
~~~~~~~

Bifrost needs to be updated to install dependencies using the stable branch.
`Example for Victoria <https://review.opendev.org/#/c/756289/>`_. The upper
constraints file referenced in ``scripts/install-deps.sh`` needs to be updated
to the new release.

For all releases
----------------

For all releases, whether or not it results in a stable branch:

* update the specs repo to mark any specs completed in the release as
  implemented.

* remove any -2s on patches that were blocked until after the release.
