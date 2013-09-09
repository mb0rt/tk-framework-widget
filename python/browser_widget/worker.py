# Copyright (c) 2013 Shotgun Software Inc.
# 
# CONFIDENTIAL AND PROPRIETARY
# 
# This work is provided "AS IS" and subject to the Shotgun Pipeline Toolkit 
# Source Code License included in this distribution package. See LICENSE.
# By accessing, using, copying or modifying this work you indicate your 
# agreement to the Shotgun Pipeline Toolkit Source Code License. All rights 
# not expressly granted therein are reserved by Shotgun Software Inc.

import os
import urllib
import uuid
import sys

from tank.platform.qt import QtCore, QtGui

class Worker(QtCore.QThread):
    """
    Background worker class
    """
    
    work_completed = QtCore.Signal(str, dict)
    work_failure = QtCore.Signal(str, str)
    
    def __init__(self, app, parent=None):
        """
        Construction
        """
        QtCore.QThread.__init__(self, parent)
        self._execute_tasks = True
        self._app = app
        
        self._queue_mutex = QtCore.QMutex()
        self._queue = []
        self._receivers = {}
        
        self._wait_condition = QtCore.QWaitCondition()
        
    def stop(self, wait_for_completion=True):
        """
        Stops the worker, run this before shutdown
        """
        self._execute_tasks = False
        self._wait_condition.wakeAll()
        if wait_for_completion:
            self.wait()

    def clear(self):
        """
        Empties the queue
        """
        self._queue_mutex.lock()
        try:
            self._queue = []
        finally:
            self._queue_mutex.unlock()
        
    def queue_work(self, worker_fn, params, asap=False):
        """
        Queues up some work.
        Returns a unique identifier to identify this item 
        """
        uid = uuid.uuid4().hex
        
        work = {"id": uid, "fn": worker_fn, "params": params}
        self._queue_mutex.lock()
        try:
            if asap:
                # first in the queue
                self._queue.insert(0, work)
            else:
                self._queue.append(work)
        finally:
            self._queue_mutex.unlock()

        self._wait_condition.wakeAll()
        
        return uid

    ############################################################################################
    #

    def run(self):

        while self._execute_tasks:
            
            # get the next item to process:
            item_to_process = None
            self._queue_mutex.lock()
            try:
                if len(self._queue) == 0:
                    # wait for some more work - this unlocks the mutex
                    # until the wait condition is signalled where it
                    # will then attempt to obtain a lock before returning
                    self._wait_condition.wait(self._queue_mutex)
                    
                    if len(self._queue) == 0:
                        # still nothing in the queue!
                        continue
                
                item_to_process = self._queue.pop(0)
            finally:
                self._queue_mutex.unlock()

            if not self._execute_tasks:
                break

            # ok, have something to do so lets do it:
            data = None
            try:
                # process the item:
                data = item_to_process["fn"](item_to_process["params"])
            except Exception, e:
                if self._execute_tasks:
                    self.work_failure.emit(item_to_process["id"], "An error occured: %s" % e)
            else:
                if self._execute_tasks:
                    self.work_completed.emit(item_to_process["id"], data)
                