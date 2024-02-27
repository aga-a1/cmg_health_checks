import paramiko
import time
import re
import yaml
import sys
from cmg_query.logger import logger
from cmg_query import error_codes as error_codes
# Hello World


class CmgQuery:
    def __init__(self):
        self.__client = None
        self.__channel = None

        self.__config_file_name = self.__config_file()
        self.__config_file = self.__read_config_file(self.__config_file_name)
        self.__ip = self.__config_file['host']['ip']
        self.__port = self.__config_file['host']['port']
        self.__username = self.__config_file['host']['username']
        self.__password = self.__config_file['host']['password']

        # Todo: shall be lowercase
        self.MAX_RECV = 23
        self.RECV_BUFSIZE = 4096
        self.READ_DELAY = 0.1
        self.cmg_ssh_prompt = '#'   # Todo: this probably shall be changed to 'hostname + #'?!
        # CONTINUE_TEXT = 'Press any key to continue'
        # Todo: why does the below string work?
        self.cmg_continue_text = 'Press any key to continue'
        try:
            self.__outfile = open('myfile.txt', 'w')
        except Exception as error:
            logger.error(error)
            exit(1)

    def __del__(self):
        if self.__outfile:
            self.__outfile.close()
        self.disconnect()

    def get_client(self):
        return self.__client

    def __config_file(self):
        # check if the config file has been provided in the command line
        # if not, exit with an error code
        if len(sys.argv) == 2:
            config_file = sys.argv[1]
            # logger.error(error_codes.error_codes['ERR_NO_CONFIG_FILE']['error_message'])
            logger.info('no config file has been provided at command line')
            exit(1)
        else:
            # config_file = 'cfg\\tests_dev.yaml'
            config_file = '/home/runner/work/cmg_health_checks/cmg_health_checks/cfg/tests_dev.yaml'
            logger.info('no config file in argv, using ' + config_file)
        return config_file

    def __read_config_file(self, config_file_name: str):
        try:
            with open(config_file_name, 'r') as f:
                config_file = yaml.safe_load(f)
        except Exception as error:
            logger.error(error)
            exit(1)

        return config_file

    def connect(self, ip: str = None) -> str:
        if ip:
            self.__ip = ip
        logger.info('trying to connect to ' + self.__ip + ':' + str(self.__port))
        self.__client = paramiko.client.SSHClient()
        self.__client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        # Todo: shall this be changed to
        #  https://stackoverflow.com/questions/7159644/does-paramiko-close-ssh-connection-on-a-non-paramiko-exception
        try:
            self.__client.connect(self.__ip, self.__port, self.__username, self.__password)
        except Exception as error:
            # logger.error(error_codes.error_codes['ERR_UNABLE_TO_CONNECT']['error_message'])
            logger.error(error)
            # exit(error_codes.error_codes['ERR_UNABLE_TO_CONNECT']['exit_code'])
            exit(1)
        logger.info('connected')
        self.__channel = self.__client.invoke_shell()
        output = self.__read_until_prompt(self.__channel)
        logger.debug(output)

        return output

    def disconnect(self):
        # Todo: if self.__client doesn't work, can't figure out how to check whether it's closed or not
        if self.__client:
            logger.info('closing ssh connection to' + self.__ip + ':' + str(self.__port))
            self.__client.close()
            self.__client = None    # Todo: not sure if this is the best solution?!
            # Todo: the idea comes from chatgpt, so don't blame me

    def __read_until_prompt(self, channel):
        logger.debug('__read_until_prompt')
        output = ""
        prompt = False
        for i in range(0, self.MAX_RECV):
            recvd = ""
            while channel.recv_ready():
                recvd = recvd + channel.recv(self.RECV_BUFSIZE).decode("utf-8")
            output = output + recvd
            if self.cmg_ssh_prompt in recvd:
                # Todo: this needs to be checked in more detail
                prompt = True
                logger.debug('ssh prompt found found in cmg_output')
                break
            if self.cmg_continue_text in recvd:
                # Todo: this needs to be checked in more detail
                logger.debug('continue text found in cmg_output')
                channel.sendall("a")  # to show more output
            time.sleep(self.READ_DELAY)
        if not prompt:
            # Todo: this needs to be checked in more detail
            print("Did not receive prompt. ")

        return output

    def __cmg_output(self, _cmd):
        result = ""
        # Todo: is \r also needed for the real CMG and does it work?!
        self.__channel.sendall(_cmd + "\r\n")
        try:
            result = self.__read_until_prompt(self.__channel)
        except Exception as error:
            print("An exception occurred:", error)
        return result

    def test_pings(self):
        # iterates through 'test_pings' from the config file
        # and executes each ping towards the configured cmg
        # the result is written to the output file
        # Todo: error handling if command is wrong
        ping_commands = self.__config_file['test_pings']
        for ping_command in ping_commands:
            cmg_output = self.__cmg_output(ping_command)
            logger.debug(cmg_output)
            result = self.__ping_result(ping_command, cmg_output)
            self.__outfile.write(str(result) + '\n')

    def __ping_result(self, command, cmg_output):
        # searches the string '0.00% packet loss' within the output received from the CMG
        # '0.00% packet loss' means the test has passed
        for line in cmg_output.split('\r\n'):
            if 'packet loss' in line:
                packet_loss = line.split(', ')[2]
        if '0.00% packet loss' in packet_loss:
            return 'OK', packet_loss, command
        else:
            return 'NOK', packet_loss, command

    def __number_of_bfd_sessions_from_cmg_footer(self, cmg_output: str) -> int:
        # parses the output of the CMG and returns the number of BFD sessions
        # command executed on CMG: show router 6203 bfd session
        # 'No. of BFD sessions: 4' - can be found in the CMG output
        # returns 4 (in this example)
        number_of_bfd_sessions = re.findall('No. of BFD sessions: (.*?)\r\n', cmg_output, flags=re.S)
        return int(number_of_bfd_sessions[0])

    def __bfd_sessions(self, command: str, cmg_output: str) -> list:
        # cmg_output: the whole output from a CMG as string
        # command executed on CMG: show router 6203 bfd session
        # returns a list of dictionaries, each dictionary contains a bfd session
        result = re.findall('-------------------------------------------------------------------------------\r\n(.*?)'
                            '-------------------------------------------------------------------------------\r\n',
                            cmg_output, flags=re.S)
        result_tuple = result[0].strip()
        linecounter = 0
        bfd_sessions = []
        for line in result_tuple.split('\r\n'):
            logger.debug(str(linecounter) + ': ' + repr(line))
            if self.cmg_continue_text in line:
                # Press any key ... is still in the string although it is not seen on the screen anymore
                # 'Press any key to continue (Q to quit)\x00\r                                      \rCMG901101_VOVI_LB2NET2AL1                            Up     47848318   39095849'
                logger.info('cmg_continue_text found: ' + repr(line))
                line = line.replace('Press any key to continue (Q to quit)\x00\r                                      \r', '')
                logger.info('replaced line without cmg_continue_text: ' + repr(line))
            if linecounter % 4 == 0:  # 1st line
                bfd_session = {}
                bfd_session['session_id'], bfd_session['state'], bfd_session['tx_pkts'], bfd_session[
                    'rx_pkts'] = line.split()
            if linecounter % 4 == 1:  # 2nd line
                # Todo: RemAddr / Info / SdpId: VcId -> type might vary?!
                bfd_session['rem_addr'], bfd_session['multipl'], bfd_session['tx_intvl'], bfd_session[
                    'rx_intvl'] = line.split()
            if linecounter % 4 == 2:  # 3rd line
                bfd_session['protocols'], bfd_session['type'], bfd_session['lag__port'], bfd_session[
                    'lag_id'] = line.split()
            if linecounter % 4 == 3:  # 4th line
                bfd_session['loc_addr'] = line.split()[0]
                bfd_sessions.append(bfd_session)
            linecounter += 1

        logger.debug('bfd_sessions from cmg_output footer: ' + str(self.__number_of_bfd_sessions_from_cmg_footer(cmg_output)))
        logger.debug('bfd_sessions counted from list: ' + str(len(bfd_sessions)))
        number_of_bfd_sessions_counted = int(len(bfd_sessions))
        number_of_bfd_sessions_from_output = self.__number_of_bfd_sessions_from_cmg_footer(cmg_output)

        if number_of_bfd_sessions_counted == number_of_bfd_sessions_from_output:
            result, result_bfd_sessions = self.__check_bfd_sessions(bfd_sessions)
            logger.debug(result + ', ' + str(result_bfd_sessions) + ', ' + command)
            self.__outfile.write(result + ', ' + 'all ' + str(
                number_of_bfd_sessions_counted) + ' bfd sessions are Up' + ', ' + command + '\n')
        else:
            # result_bfd_sessions = self.__check_bfd_sessions(bfd_sessions[1])
            result, result_bfd_sessions = self.__check_bfd_sessions(bfd_sessions)
            result = 'NOK'  # overwrite the result, as at least one session is missing
            logger.debug(result + ', ' + str(result_bfd_sessions) + ', ' + command)
            # self.__outfile.write(result + ', ' + str(result_bfd_sessions) + ', ' + command + '\n')
            self.__outfile.write(result + ', ' + 'No. of BFD sessions: ' + str(number_of_bfd_sessions_from_output) +
                                 ' counted: ' + str(number_of_bfd_sessions_counted) + ', ' + command + '\n')

    def __check_bfd_sessions(self, bfd_sessions: list) -> tuple[str, list]:
        # checks if all bfd sessions are up
        result_bfd_sessions = []
        result = ''
        logger.debug(bfd_sessions)
        for bfd_session in bfd_sessions:
            # result_bfd_sessions[bfd_session['session_id']] = bfd_session['state']
            session = {bfd_session['session_id']: bfd_session['state']}
            result_bfd_sessions.append(session)
        for bfd_session in bfd_sessions:
            if bfd_session['state'] != 'Up':
                result = 'NOK'
                break
                # Todo: add output do info.logs
            else:
                result = 'OK'
        return result, result_bfd_sessions

    def test_bfd_sessions(self):
        # Todo: error handling if command is wrong
        show_router_commands = self.__config_file['test_bfd_sessions']
        for show_router_command in show_router_commands:
            cmg_output = self.__cmg_output(show_router_command)
            logger.debug(cmg_output)
            self.__bfd_sessions(show_router_command, cmg_output)
