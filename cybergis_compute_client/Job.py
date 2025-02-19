from .MarkdownTable import MarkdownTable  # noqa
import time
import json
from os import system, name
from IPython.display import display, clear_output, Markdown
import ipywidgets as widgets


class Job:
    """
    Job class

    Attributes:
        client (obj): Client that this job requests information from
        maintainer (obj): Maintainer pool that this job is in
        isJupyter (bool): Whether or not this is running in Jupyter
        jupyterhubApiToken (str): API token needed to send requests
            using the JupyterHub API
        id (str): Id assigned to this job by the client
        hpc (str): HPC that this job will be submitted to
    """
    # static variables
    basicEventTypes = [
        'JOB_QUEUED', 'JOB_REGISTERED', 'JOB_INIT',
        'GLOBUS_TRANSFER_INIT_SUCCESS', 'JOB_ENDED', 'JOB_FAILED']

    def __init__(self, maintainer=None, hpc=None, id=None, hpcUsername=None, hpcPassword=None,
                 client=None, isJupyter=None, jupyterhubApiToken=None, printJob=True):
        # TODO: we can make this better
        if (jupyterhubApiToken is None):
            raise Exception('please login to jupyter first')
        self.client = client
        self.maintainer = maintainer
        self.isJupyter = isJupyter
        self.jupyterhubApiToken = jupyterhubApiToken

        job = None
        if (id is None):
            # create new job
            if maintainer is None:
                raise Exception('maintainer cannot by NoneType')

            req = {'maintainer': maintainer, 'jupyterhubApiToken': jupyterhubApiToken}
            if (hpc is not None):
                req['hpc'] = hpc

            if (hpcUsername is None):
                job = self.client.request('POST', '/job', req)
            else:
                req['user'] = hpcUsername
                req['password'] = hpcPassword
                job = self.client.request('POST', '/job', req)

            hpc = job['hpc']
            id = job['id']
        else:
            # reinstate existing job
            job = self.client.request('GET', '/job/' + id, {'jupyterhubApiToken': jupyterhubApiToken})
            hpc = job['hpc']

        if (hpcPassword is not None):
            print('⚠️ HPC password input detected, change your code to use .get_job_by_id() instead')
            print('🙅‍♂️ it\'s not safe to distribute code with login credentials')

        self.id = id
        self.hpc = hpc
        if printJob:
            self._print_job_formatted(job)

    def submit(self):
        """
        Submits this job to the client, and prints the output

        Returns:
            Job: This job
        """
        body = {'jupyterhubApiToken': self.jupyterhubApiToken}
        job = self.client.request('POST', '/job/' + self.id + '/submit', body)
        print('✅ job submitted')
        self._print_job_formatted(job)
        return self

    def set(self, localExecutableFolder=None, localDataFolder=None, localResultFolder=None, param=None, env=None,
            slurm=None, printJob=True):
        """
        PUT requests information about this job to the client
        so it can be submitted to the hpc. Displays information
        about this job unless specified otherwise.

        Args:
            executableFolder (str): Path of the executable folder
            dataFolder (str): Path of the data folder
            resultFolder (str): Path of the result folder
            param (dict): Rules for input data
            env (dict): Enviorment variables required by the appliation
            slurm (dict): Slurm input rules
            printJob (bool): If the status of the job should be printed
        """
        body = {'jupyterhubApiToken': self.jupyterhubApiToken}

        if localExecutableFolder:
            body['localExecutableFolder'] = localExecutableFolder
        if localDataFolder:
            body['localDataFolder'] = localDataFolder
        if localResultFolder:
            body['localResultFolder'] = localResultFolder
        if param:
            body['param'] = param
        if env:
            body['env'] = env
        if slurm:
            body['slurm'] = slurm

        if (len(list(body)) == 1):
            print('❌ please set at least one parmeter')

        job = self.client.request('PUT', '/job/' + self.id, body)
        if printJob:
            self._print_job(job)

    def events(
        self, raw=False,
            basic=True,
            refreshRateInSeconds=10):
        """
        While the job is running, display the events generated by the client

        Args:
            raw (bool): If true, return a list of the events
            generated by status
            liveOutput (bool):
            basic (bool): If true, exclude non-basicEventType events
            RefreshRateInSeconds (int): Number of seconds to wait before
            refreshing status

        Todo:
            Modify function to include liveOutput or remove it
            from the arguments
        """
        if raw:
            return self.status(raw=True)['events']

        isEnd = False
        jobFailure = False
        while (not isEnd):
            self._clear()
            status = self.status(raw=True)
            out = status['events']
            headers = ['types', 'message', 'time']
            events = []
            for o in out:
                # if o['type'] not in self.basicEventTypes and basic:
                #     continue
                events.append([
                    o['type'],
                    o['message'],
                    o['createdAt']
                ])
                isEnd = isEnd or o['type'] == 'JOB_ENDED' or o[
                    'type'] == 'JOB_FAILED'
                if isEnd and o['type'] == 'JOB_FAILED':
                    jobFailure = True

            print('📮 Job ID: ' + self.id)
            if 'slurmId' in status:
                print('🤖 Slurm ID: ' + str(status['slurmId']))

            def markdown_widget(text):
                out = widgets.Output()
                with out:
                    display(Markdown(text))
                return out
            markdown = MarkdownTable.render(events, headers)
            markdown_table = markdown_widget(markdown)
            table_exp = widgets.Accordion(children=[markdown_table], selected_index=None)
            table_exp.set_title(0, "See events")
            if len(events) > 0:
                if self.isJupyter:
                    display(table_exp)
                else:
                    print(markdown)

            if not isEnd:
                time.sleep(refreshRateInSeconds)
        return jobFailure

    def logs(self, raw=False, liveOutput=True, refreshRateInSeconds=15):
        """
        While the job is running, display the logs generated by the client.

        Args:
            raw (bool): If true, return a list of the events
            generated by status
            liveOutput (bool):
            RefreshRateInSeconds (int): Number of seconds to wait
            before refreshing status

        Returns:
            list: List of logs generated by the client.
            Only returned if raw is true.

        Todo:
            Modify function to include liveOutput
            or remove it from the arguments
        """
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
                isEnd = isEnd or o['type'] == 'JOB_ENDED' or o[
                    'type'] == 'JOB_FAILED'

            for o in status['logs']:
                i = [
                    o['message'],
                    o['createdAt']
                ]
                logs.append(i)

            print('📮 Job ID: ' + self.id)
            if 'slurmId' in status:
                print('🤖 Slurm ID: ' + str(status['slurmId']))

            def markdown_widget(text):
                out = widgets.Output()
                with out:
                    display(Markdown(text))
                return out
            markdown = MarkdownTable.render(logs, headers)
            markdown_table = markdown_widget(markdown)
            table_exp = widgets.Accordion(children=[markdown_table], selected_index=None)
            table_exp.set_title(0, "See logs")
            if len(logs) > 0:
                if self.isJupyter:
                    display(table_exp)
                else:
                    print(markdown)
            if not isEnd:
                time.sleep(refreshRateInSeconds)

    def status(self, raw=False):
        """
        Displays the status of this job, and returns it if specified.

        Args:
            raw (bool): If information about this job should be returned

        Returns:
            dict: Infomation about this job returned by
            the client. This includes the job's 'id', 'hpc',
            'executableFolder', 'dataFolder', 'resultFolder',
            'param', 'slurm', 'userId', 'maintainer', 'createdAt', and 'events'

        Raises:
            Exception: If the 'id' attribute is None
        """
        if self.id is None:
            raise Exception('missing job ID, submit/register job first')

        job = self.client.request('GET', '/job/' + self.id, {
            'jupyterhubApiToken': self.jupyterhubApiToken
        })

        if raw:
            return job
        self._print_job_formatted(job)

    def result_folder_content(self):
        """
        Returns the results from the job

        Returns:
            dict: Results from running the job

        Raises:
            Exception: If the id is None
        """
        if self.id is None:
            raise Exception('missing job ID, submit/register job first')
        out = self.client.request('GET', '/job/' + self.id + '/result-folder-content', {'jupyterhubApiToken': self.jupyterhubApiToken})
        return out

    def download_result_folder_by_globus(self, localPath=None, localEndpoint=None, remotePath=None, raw=False):
        """
        Downloads the folder with results from the job using Globus

        Args:
            remotePath (string): Path to the remote result folder
            raw (bool): If the function should return the
            output from the client

        Returns:
            dict: Output from the client when downloading the
            results using globus. Only returned when raw is true.

        Raises:
            Exception: If the job ID is None
            Exception: If the key 'resultFolder' is not returned with status
            Exception: If the result folder is formatted improperly
        """
        if self.id is None:
            raise Exception('missing job ID, submit/register job first')

        jobStatus = self.status(raw=True)
        if 'remoteResultFolder' not in jobStatus:
            raise Exception('executable folder is not ready')
        folderId = jobStatus['remoteResultFolder']['id']

        # init globus transfer
        self.client.request('POST', '/folder/' + folderId + '/download/globus-init', {
            "jobId": self.id,
            "jupyterhubApiToken": self.jupyterhubApiToken,
            "fromPath": remotePath,
            "toPath": localPath,
            "toEndpoint": localEndpoint
        })

        status = None
        while status not in ['SUCCEEDED', 'FAILED']:
            self._clear()
            print('⏳ waiting for file to download using Globus')
            out = self.client.request('GET', '/folder/' + folderId + '/download/globus-status', {
                "jupyterhubApiToken": self.jupyterhubApiToken
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

    # Helpers
    def _clear(self):
        """
        Clears output
        """
        if self.isJupyter:
            clear_output(wait=True)
        # for windows
        if name == 'nt':
            _ = system('cls')
        # for mac and linux(here, os.name is 'posix')
        else:
            _ = system('clear')

    def _print_job(self, job):
        """
        Displays information about this job

        Args:
            job (dict): Information about this job returned by the client
        """
        if job is None:
            return
        headers = [
            'id', 'slurmId', 'hpc', 'remoteExecutableFolder', 'remoteDataFolder',
            'remoteResultFolder', 'param', 'slurm', 'userId', 'maintainer',
            'createdAt']
        data = [[
            job['id'],
            job['slurmId'],
            job['hpc'],
            job['remoteExecutableFolder'],
            job['remoteDataFolder'],
            job['remoteResultFolder'],
            json.dumps(job['param']),
            json.dumps(job['slurm']),
            job['userId'],
            job['maintainer'],
            job['createdAt'],
        ]]

        if self.isJupyter:
            display(Markdown(MarkdownTable.render(data, headers)))
        else:
            print(MarkdownTable.render(data, headers))

    def _print_job_formatted(self, job):
        """
        Displays information about the job formatted in a way that can be read with no horizonal scroll bar
        """

        if job is None:
            return
        if job['localExecutableFolder'] is None:
            modelName = "None"
        else:
            modelName = job['localExecutableFolder']['gitId']
        headersCol1 = [
            'id', 'slurmId', 'hpc', 'remoteExecutableFolder', 'remoteDataFolder',
            'remoteResultFolder']
        headersCol2 = [
            'param', 'slurm', 'userId', 'maintainer',
            'createdAt', 'modelName']
        dataCol1 = [[
            job['id'],
            job['slurmId'],
            job['hpc'],
            job['remoteExecutableFolder'],
            job['remoteDataFolder'],
            job['remoteResultFolder'],
        ]]

        dataCol2 = [[
            json.dumps(job['param']),
            json.dumps(job['slurm']),
            job['userId'],
            job['maintainer'],
            job['createdAt'],
            modelName
        ]]

        if self.isJupyter:
            display(Markdown(MarkdownTable.render(dataCol1, headersCol1)))
            display(Markdown(MarkdownTable.render(dataCol2, headersCol2)))
        else:
            print(MarkdownTable.render(dataCol1, headersCol1))
            print(MarkdownTable.render(dataCol2, headersCol2))
