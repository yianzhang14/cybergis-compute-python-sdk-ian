from .Client import *
from .JAT import *
from .Zip import *
import time
import os
import json
from os import system, name
from tabulate import tabulate
from IPython.display import HTML, display, clear_output


class Job:
    # static variables
    basicEventTypes = ['JOB_QUEUED', 'JOB_REGISTERED', 'JOB_INIT', 'GLOBUS_TRANSFER_INIT_SUCCESS', 'JOB_ENDED', 'JOB_FAILED']

    def __init__(self, maintainer=None, hpc=None, id=None, secretToken=None, hpcUsername=None, hpcPassword=None, client=None, isJupyter=None, jupyterhubApiToken=None, printJob=True):
        self.JAT = JAT()
        self.client = client
        self.maintainer = maintainer
        self.isJupyter = isJupyter
        self.jupyterhubApiToken = jupyterhubApiToken

        job = None
        if (secretToken is None):
            if maintainer is None:
                raise Exception('maintainer cannot by NoneType')

            req = {'maintainer': maintainer}
            if (hpc is not None):
                req['hpc'] = hpc
            if (jupyterhubApiToken is not None):
                req['jupyterhubApiToken'] = jupyterhubApiToken

            if (hpcUsername is None):
                job = self.client.request('POST', '/job', req)
            else:
                req['user'] = hpcUsername
                req['password'] = hpcPassword
                job = self.client.request('POST', '/job', req)

            hpc = job['hpc']
            secretToken = job['secretToken']
            id = job['id']
            self.JAT.init('md5', id, secretToken)
        else:
            self.JAT.init('md5', id, secretToken)
            job = self.client.request('GET', '/job/get-by-token', {'accessToken': self.JAT.getAccessToken()})
            hpc = job['hpc']

        if (hpcPassword is not None):
            print('⚠️ HPC password input detected, change your code to use .get_job_by_id() instead')
            print('🙅‍♂️ it\'s not safe to distribute code with login credentials')

        self.id = id
        self.hpc = hpc
        if printJob:
            self._print_job(job)

    def submit(self):
        body = {'accessToken': self.JAT.getAccessToken()}
        if (self.jupyterhubApiToken is not None):
            body['jupyterhubApiToken'] = self.jupyterhubApiToken
        job = self.client.request('POST', '/job/' + self.id + '/submit', body)
        print('✅ job submitted')
        self._print_job(job)
        return self

    def upload_executable_folder(self, folder_path):
        folder_path = os.path.abspath(folder_path)

        zip = Zip()
        for root, dirs, files in os.walk(folder_path, followlinks=True):
            for f in files:
                with open(os.path.join(root, f), 'rb') as i:
                    p = os.path.join(root.replace(folder_path, ''), f)
                    zip.append(p, i.read())

        response = self.client.upload('/file', {
            'accessToken': self.JAT.getAccessToken()
        }, zip.read())
        self.set(executableFolder=response['file'], printJob=True)
        return response

    def set(self, executableFolder=None, dataFolder=None, resultFolder=None, param=None, env=None, slurm=None, printJob=True):
        body = {'jupyterhubApiToken': self.jupyterhubApiToken}

        if executableFolder:
            body['executableFolder'] = executableFolder
        if dataFolder:
            body['dataFolder'] = dataFolder
        if resultFolder:
            body['resultFolder'] = resultFolder
        if param:
            body['param'] = param
        if env:
            body['env'] = env
        if slurm:
            body['slurm'] = slurm

        if (len(list(body)) == 1):
            print('❌ please set at least one parmeter')

        body['accessToken'] = self.JAT.getAccessToken()
        job = self.client.request('PUT', '/job/' + self.id, body)
        if printJob:
            self._print_job(job)

    def events(self, raw=False, liveOutput=True, basic=True, refreshRateInSeconds=10):
        if raw:
            return self.status(raw=True)['events']

        isEnd = False
        while (not isEnd):
            self._clear()
            status = self.status(raw=True)
            out = status['events']
            headers = ['types', 'message', 'time']
            events = []
            for o in out:
                if o['type'] not in self.basicEventTypes and basic:
                    continue

                i = [
                    o['type'],
                    o['message'],
                    o['createdAt']
                ]

                events.append(i)
                isEnd = isEnd or o['type'] == 'JOB_ENDED' or o['type'] == 'JOB_FAILED'

            print('📮 Job ID: ' + self.id)
            if 'slurmId' in status:
                print('🤖 Slurm ID: ' + str(status['slurmId']))
            if self.isJupyter:
                display(HTML(tabulate(events, headers, tablefmt='html')))
            else:
                print(tabulate(events, headers, tablefmt='presto'))

            if not isEnd:
                time.sleep(refreshRateInSeconds)

    def logs(self, raw=False, liveOutput=True, refreshRateInSeconds=15):
        if raw:
            return self.status(raw=True)['logs']

        logs = []
        isEnd = False
        while (not isEnd):
            self._clear()
            status = self.status(raw=True)
            headers = ['message', 'time']
            logs = []

            for o in status['events']:
                isEnd = isEnd or o['type'] == 'JOB_ENDED' or o['type'] == 'JOB_FAILED'

            for o in status['logs']:
                i = [
                    o['message'],
                    o['createdAt']
                ]
                logs.append(i)

            print('📮 Job ID: ' + self.id)
            if 'slurmId' in status:
                print('🤖 Slurm ID: ' + str(status['slurmId']))
            if self.isJupyter:
                display(HTML(tabulate(logs, headers, numalign='left', stralign='left', colalign=('left', 'left'), tablefmt='html').replace('<td>', "<td style='text-align:left'>")))
            else:
                print(tabulate(logs, headers, tablefmt='presto'))

            if not isEnd:
                time.sleep(refreshRateInSeconds)

    def status(self, raw=False):
        if self.id is None:
            raise Exception('missing job ID, submit/register job first')

        job = self.client.request('GET', '/job/' + self.id, {
            'accessToken': self.JAT.getAccessToken()
        })

        if raw:
            return job
        self._print_job(job)

    def result_folder_content(self):
        if self.id is None:
            raise Exception('missing job ID, submit/register job first')
        out = self.client.request('GET', '/job/' + self.id + '/result-folder-content', {
            'accessToken': self.JAT.getAccessToken()
        })
        return out

    def download_result_folder(self, localPath=None, remotePath=None, raw=False):
        if self.id is None:
            raise Exception('missing job ID, submit/register job first')

        jobStatus = self.status(raw=True)
        if 'resultFolder' not in jobStatus:
            raise Exception('executable folder is not ready')

        i = jobStatus['resultFolder'].split('://')
        if (len(i) != 2):
            raise Exception('invalid result folder formate provided')

        fileType = i[0]
        fileId = i[1]

        if (fileType == 'globus'):
            status = None
            while status not in ['SUCCEEDED', 'FAILED']:
                self._clear()
                print('⏳ waiting for file to download using Globus')
                out = self.client.request('GET', '/file/result-folder/globus-download', {
                    "accessToken": self.JAT.getAccessToken(),
                    "downloadTo": jobStatus['resultFolder'],
                    "downloadFrom": remotePath
                })
                status = out['status']
                if raw:
                    return out
            # exit loop
            self._clear()
            if status == 'SUCCEEDED':
                print('✅ download success!')
            else:
                print('❌ download fail!')

        if (fileType == 'local'):
            localPath = os.path.join(localPath, fileId)
            localPath = self.client.download('/file/result-folder/direct-download', {
                "accessToken": self.JAT.getAccessToken()
            }, localPath)
            print('file successfully downloaded under: ' + localPath)
            return localPath

    def query_globus_task_status(self):
        if self.id is None:
            raise Exception('missing job ID, submit/register job first')
        return self.client.request('GET', '/file/' + self.id + '/globus_task_status', {
            'accessToken': self.JAT.getAccessToken()
        })

    # Integrated functions

    # HACK: back compatability
    def downloadResultFolder(self, dir=None):
        return self.download_result_folder(dir)

    # Helpers
    def _clear(self):
        if self.isJupyter:
            clear_output(wait=True)
        # for windows
        if name == 'nt':
            _ = system('cls')
        # for mac and linux(here, os.name is 'posix')
        else:
            _ = system('clear')

    def _print_job(self, job):
        if job is None:
            return
        headers = ['id', 'slurmId', 'hpc', 'executableFolder', 'dataFolder', 'resultFolder', 'param', 'slurm', 'userId', 'maintainer', 'createdAt']
        data = [[
            job['id'],
            job['slurmId'],
            job['hpc'],
            job['executableFolder'],
            job['dataFolder'],
            job['resultFolder'],
            json.dumps(job['param']),
            json.dumps(job['slurm']),
            job['userId'],
            job['maintainer'],
            job['createdAt'],
        ]]

        if self.isJupyter:
            display(HTML(tabulate(data, headers, numalign='left', stralign='left', colalign=('left', 'left'), tablefmt='html').replace('<td>', '<td style="text-align:left">').replace('<th>', '<th style="text-align:left">')))
        else:
            print(tabulate(data, headers, tablefmt="presto"))
