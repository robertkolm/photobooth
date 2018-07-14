#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Photobooth - a flexible photo booth software
# Copyright (C) 2018  Balthasar Reuter <photobooth at re - web dot eu>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see <http://www.gnu.org/licenses/>.

import logging

from PIL import Image, ImageOps

from ..PictureDimensions import PictureDimensions
from .. import StateMachine
from ..Threading import Workers

# Available camera modules as tuples of (config name, module name, class name)
modules = (
    ('python-gphoto2', 'CameraGphoto2', 'CameraGphoto2'),
    ('gphoto2-cffi', 'CameraGphoto2Cffi', 'CameraGphoto2Cffi'),
    ('gphoto2-commandline', 'CameraGphoto2CommandLine',
     'CameraGphoto2CommandLine'),
    ('opencv', 'CameraOpenCV', 'CameraOpenCV'),
    ('picamera', 'CameraPicamera', 'CameraPicamera'),
    ('dummy', 'CameraDummy', 'CameraDummy'))


class Camera:

    def __init__(self, config, comm, CameraModule):

        super().__init__()

        self._comm = comm
        self._cap = CameraModule()
        self._pic_dims = PictureDimensions(config, self._cap.getPicture().size)

        self._is_preview = (config.getBool('Photobooth', 'show_preview') and
                            self._cap.hasPreview)
        self._is_keep_pictures = config.getBool('Photobooth', 'keep_pictures')

        logging.info('Using camera {} preview functionality'.format(
            'with' if self.is_preview else 'without'))

        self.setIdle()

    def teardown(self):

        self._cap.cleanup()

    def run(self):

        for state in self._comm.iter(Workers.CAMERA):
            self.handleState(state)

    def handleState(self, state):

        if isinstance(state, StateMachine.GreeterState):
            self.prepareCapture()
        elif isinstance(state, StateMachine.CountdownState):
            self.capturePreview()
        elif isinstance(state, StateMachine.CaptureState):
            self.capturePicture()
        elif isinstance(state, StateMachine.AssembleState):
            self.assemblePicture()
        elif isinstance(state, StateMachine.TeardownState):
            self.teardown()

    def setActive(self):

        self._cap.setActive()

    def setIdle(self):

        if self._cap.hasIdle:
            self._cap.setIdle()

    def prepareCapture(self):

        self.setActive()
        self._pictures = []

    def capturePreview(self):

        if self._is_preview:
            while self._comm.empty(Workers.CAMERA):
                picture = ImageOps.mirror(self._cap.getPreview())
                self._comm.send(Workers.GUI,
                                StateMachine.CameraEvent('preview', picture))

    def capturePicture(self):

        self.setIdle()
        picture = self._cap.getPicture()
        self._pictures.append(picture)
        self.setActive()

        if self._is_keep_pictures:
            self._comm.send(Workers.WORKER,
                            StateMachine.CameraEvent('capture', picture))

        if len(self._pictures) < self._pic_dims.totalNumPictures:
            self._comm.send(Workers.MASTER,
                            StateMachine.CameraEvent('countdown', picture))
        else:
            self._comm.send(Workers.MASTER,
                            StateMachine.CameraEvent('assemble', picture))

    def assemblePicture(self):

        self.setIdle()

        picture = Image.new('RGB', self._pic_dims.outputSize, (255, 255, 255))
        for i in range(self._pic_dims.totalNumPictures):
            resized = self._pictures[i].resize(self._pic_dims.thumbnailSize)
            picture.paste(resized, self._pic_dims.thumbnailOffset[i])

        self._comm.send(Workers.MASTER,
                        StateMachine.CameraEvent('review', picture))
        self._pictures = []
