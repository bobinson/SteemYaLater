import os, certifi, csv, datetime, hashlib, io, json, logging, pycurl, random, re, time, wget, urllib3, shutil, socket, sys

from beem import Steem
from beem.account import Account
from beem.amount import Amount
from beem.comment import Comment
from beem.exceptions import AccountDoesNotExistsException, ContentDoesNotExistsException
from beem.nodelist import NodeList
from beem.instance import set_shared_steem_instance


global working_dir, pauseTimeInit, persist

nodes = NodeList().get_nodes()
stm = Steem(node='https://anyx.io')
#stm = Steem(node=nodes)
set_shared_steem_instance(stm)

# Certificate validation required for security. Prevent MITM
http = urllib3.PoolManager(
                           cert_reqs='CERT_REQUIRED',
                           ca_certs='/etc/ssl/certs/cacerts.pem'#ca_certs=certifi.where()
                           )

working_dir = os.getcwd()
logging.basicConfig(filename=datetime.datetime.now().strftime("SteemYaLater%Y%m%d-%H%M%S.log"),format='%(asctime)s %(message)s',level=logging.WARNING)

# Global Vars
persist = True
pauseTimeInit = 15

# Other variables

regex = re.compile(
        r'^(?:http|ftp)s?://' # http:// or https://
        r'(?:(?:[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?\.)+(?:[A-Z]{2,6}\.?|[A-Z0-9-]{2,}\.?)|' #domain...
        r'localhost|' #localhost...
        r'\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})' # ...or ip
        r'(?::\d+)?' # optional port
        r'(?:/?|[/?]\S+)$', re.IGNORECASE)


halfPause = int(pauseTimeInit/2)
lowPauseTime = pauseTimeInit - halfPause
upPauseTime = pauseTimeInit + halfPause

if not os.path.isdir(working_dir+"/Backups/"):
    os.mkdir(working_dir+"/Backups/")

def loadjson(filename):
    if os.path.exists(filename):
        with open(filename) as json_file:
            loadedfile = json.load(json_file)
    else:
        print(filename+" not found!")
        return
    return loadedfile

def writejson(filename,jdict):
    with open(filename, 'w') as json_file:
        json.dump(jdict, json_file)

def get_blog_entries(account_to_backup):
    blog_list = []
    acc = Account(account_to_backup,steem_instance=stm)
    if os.path.exists(working_dir+"/Backups/"+account_to_backup+"/account_to_backup.json"):
        jTx = loadjson(working_dir+"/Backups/"+account_to_backup+"/account_to_backup.json")
        if jTx:
            for json_data in jTx:
                blog_list.append(json_data)
    if blog_list:
        startIndex = blog_list[-1]['entry_id']
    else:
        startIndex = 1
    while len(acc.get_blog(startIndex,1,raw_data=True,short_entries=True)) > 0:
        chunk = acc.get_blog(startIndex,1,raw_data=True,short_entries=True)
        startIndex += 1
        for c in chunk:
            print(c)
            if c['author'] == account_to_backup:
                blog_list.append(c)
    if persist:
        writejson(working_dir+"/Backups/"+account_to_backup+"/account_to_backup.json",blog_list)
    return blog_list

# exports list to csv file
def export_csv(name,input_list):
    cwd = os.getcwd()
    filename=datetime.datetime.now().strftime(name+"%Y%m%d-%H%M%S.csv")
    keys = input_list[0].keys()
    outfile=open(cwd+'/'+filename,'w')
    writer=csv.DictWriter(outfile, keys)
    writer.writeheader()
    writer.writerows(input_list)


def get_file_hash(ref):
    md5_returned = None
    if re.match(regex,ref):
        try:
            request = get_http_response(ref)
            with request as url_to_check:
                data = url_to_check.read() # read contents of the file
                md5_returned = hashlib.md5(data).hexdigest() # pipe contents of the file through
            request.close()
        except Exception as e:
            print(e)
            logging.warning('Error obtaining '+ref+' hash w urllib3!')
            try:
                data = downloadFile(ref)
                md5_returned = hashlib.md5(data).hexdigest()
            except Exception as e:
                print(e)
                logging.warning('Error obtaining '+ref+' hash w pycurl!')
                return
    elif os.path.exists(ref):
        with open(ref, 'rb') as file_to_check:
            data = file_to_check.read() # read contents of the file
            md5_returned = hashlib.md5(data).hexdigest() # pipe contents of the file through
            file_to_check.close()
    return md5_returned

def get_http_header(url):
    if 'steemitimages.com' in url:
        headers={'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36', 'sec-fetch-dest': 'document','sec-fetch-mode': 'navigate', 'sec-fetch-site': 'none', 'sec-fetch-user': '?1'}
    else:
        headers={'user-agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36'}
    return headers

def get_http_response(url):
    header = get_http_header(url)
    request = http.request(
                'GET',
                url,
                retries=2,
                preload_content=False,
                headers=header
                )
    return request

def compare_hash(ref1,ref2): # not used but adding for future use
    try:
        k1 = get_file_hash(ref1)
        k2 = get_file_hash(ref2)
    except Exception as e:
        print(e)
        logging.warning('Error obtaining reference hash!')
        return
    if k1 == k2:
        print("Hash Match!")
        return True
    if k1 != k2:
        print("Hash Mismatch!")
        return False

def download(img,img_dir): #attempts downloading w all three providers
    status_list = []
    out_path = img_dir+'/'+img.split('/')[-1]
	if not os.path.exists(os.path.join(img_dir,img.split('/')[-1])):
	   try:
		   wget.download(img,out=out_path)
	   except Exception as e:
		   status_dict = {'id': id, 'url': img, 'wget': e, 'url3': False, 'pcurl': False}
		   status_list.append(status_dict)
		   print("wget download failed! attempting download with urllib3.")
		   try:
			   pauseTime = random.randint(lowPauseTime, upPauseTime)
			   time.sleep(pauseTime)
			   download_image(out_path,img)
		   except Exception as e:
			   print(e)
			   print("urllib3 download failed! attempting download with pycurl.")                               
			   status_dict = {'id': id, 'url': img, 'wget': False, 'url3': e, 'pcurl': False}
			   status_list.append(status_dict)
			   try:
				   downloadFile(img, out_path)
			   except Exception as e:
				   print(e)
				   print("pycurl download failed! attempting download with pycurl.")                               
				   status_dict = {'id': id, 'url': img, 'wget': False, 'url3': False, 'pcurl': e}
				   status_list.append(status_dict)
			   else:
				   file_hash = downloadFile(img)
				   hashes.append(file_hash)
				   status_dict = {'id': id, 'url': img, 'wget': False, 'url3': False, 'pcurl': True}
				   status_list.append(status_dict)
                   continue
		   else:
			   file_hash = get_file_hash(out_path)
			   hashes.append(file_hash)
			   status_dict = {'id': id, 'url': img, 'wget': False, 'url3': True, 'pcurl': False}
			   status_list.append(status_dict)
               continue
	   else:
		   file_hash = get_file_hash(out_path)
		   hashes.append(file_hash)
		   status_dict = status_dict = {'id': id, 'url': img, 'wget': True, 'url3': False, 'pcurl': False}
		   status_list.append(status_dict)

	pauseTime = random.randint(lowPauseTime, upPauseTime)
	time.sleep(pauseTime)
    return status_list

def downloadProgress(download_t, download_d, upload_t, upload_d):
    try:
        frac = float(download_d)/float(download_t)
    except:
        frac = 0
    sys.stdout.write("\r%s %3i%%" % ("Download:", frac*100)  )

def downloadFile(url, outpath=False, key_file=False, cert_file=False):
    fp = None
    fileName = url.split('/')[-1]
    curl = pycurl.Curl()
    if outpath:
        fp = open(outpath, "wb")
        curl.setopt(pycurl.WRITEDATA, fp)
    curl.setopt(pycurl.URL, url)
    headers = []
    curl.setopt(pycurl.HTTPHEADER, ['user-agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.130 Safari/537.36',
	                                'sec-fetch-dest: document',
									'sec-fetch-mode: navigate',
									'sec-fetch-site: none',
									'sec-fetch-user: ?1'])
    curl.setopt(pycurl.NOPROGRESS, 0)
    curl.setopt(pycurl.PROGRESSFUNCTION, downloadProgress)
    curl.setopt(pycurl.FOLLOWLOCATION, 1)
    curl.setopt(pycurl.MAXREDIRS, 5)
    curl.setopt(pycurl.CONNECTTIMEOUT, 6)
    curl.setopt(pycurl.TIMEOUT, 5)
    curl.setopt(pycurl.FTP_RESPONSE_TIMEOUT, 5)
    curl.setopt(pycurl.NOSIGNAL, 1)
    if key_file:
        curl.setopt(pycurl.SSLKEY, key_file)
    if cert_file:
        curl.setopt(pycurl.SSLCERT, cert_file)
    try:
        print("Start time: " + time.strftime("%c"))
        try:
            curl.perform()
        except Exception as e:
            curl.setopt(pycurl.SSL_VERIFYPEER, 0)
            curl.setopt(pycurl.SSL_VERIFYHOST, 2)
            curl.perform()
        print("\nTotal-time: " + str(curl.getinfo(curl.TOTAL_TIME)))
        print("Download speed: %.2f bytes/second" % (curl.getinfo(curl.SPEED_DOWNLOAD)))
        print("Document size: %d bytes" % (curl.getinfo(curl.SIZE_DOWNLOAD)))
    except:
        import traceback
        traceback.print_exc(file=sys.stderr)
        sys.stderr.flush()
    data = curl.perform_rb()
    curl.close()
    sys.stdout.flush()
    hash = hashlib.md5(data).hexdigest()
    if fp:
        fp.close()
    return hash

def download_image(path,url): #Download Image with urllib3
    r = get_http_response(url)
    with r, open(path, 'wb') as out_file:
        shutil.copyfileobj(r, out_file)
    r.release_conn()

def downloadProgress(download_t, download_d, upload_t, upload_d):
    try:
        frac = float(download_d)/float(download_t)
    except:
        frac = 0
    sys.stdout.write("\r%s %3i%%" % ("Download:", frac*100)  )

def get_image_hash_list(account_to_backup):
    image_hash_list = []
    for root,dir,files in os.walk(os.path.join(working_dir+"/Backups/"+account_to_backup)):
        if root.endswith('/images'):
            relative_path = root.split(account_to_backup)[-1]
            for f in files:
                md5_hash = get_file_hash(root+'/'+f)
                image_hash_dict = {'image_path': relative_path+'/'+f,'hash': md5_hash}
                image_hash_list.append(image_hash_dict)
    return image_hash_list

def download_blog_entry(blog_entry,hash_table,hashes): # accepts output from from Beem Account.get_blog(start_index=1,limit=1,raw_data=True,short_entries=True)
    status_list = []
    id = '@'+blog_entry['author']+'/'+blog_entry['permlink']
    try:
        c = Comment(id, steem_instance=stm)
    except ContentDoesNotExistsException:
        logging.warning(id+' content does not exist!')
    permlink_trucated = blog_entry['permlink'][:128] + (blog_entry['permlink'][128:] and '..') #trucate permlink to accomodate 128 character element limit
    img_dir = os.path.join(working_dir+"/Backups/"+blog_entry['author'],permlink_trucated+'/images')
    if not os.path.isdir(os.path.join(working_dir+"/Backups/"+blog_entry['author'],permlink_trucated)):
        os.mkdir(os.path.join(working_dir+"/Backups/"+blog_entry['author'],permlink_trucated))
    if not os.path.isdir(img_dir):
        os.mkdir(img_dir)
    split_body = c.body.split('\n')
    txt_path = os.path.join(working_dir+"/Backups/"+blog_entry['author'],permlink_trucated,permlink_trucated+".txt")
    if not os.path.isfile(txt_path):
        text_file = open(txt_path, "w+")
        for str in split_body:
            text_file.write(str+'\n')
        text_file.close()
    print("Backing up "+id+" images!")
    try:
        for img in c['json_metadata']['image']:
            halfPause = int(pauseTimeInit/2)
            lowPauseTime = pauseTimeInit - halfPause
            upPauseTime = pauseTimeInit + halfPause
            out_path = img_dir+'/'+img.split('/')[-1]
            if img:
                try:
                    if re.match(regex,img):
                        if '//' in img and img.count('//') < 2:
                            try:
                                domain = img.split('//')[1].split('/')[0]
                                filename = img.split('//')[1].split('/')[-1]
                                if '.' in filename:
                                    ext = img.split('//')[1].split('/')[-1].split('.')[-1] #gets file extension
                                    filename = img.split('//')[1].split('/')[-1].split('.')[-2]
                                    full_filename = filename+'.'+ext
                                else:
                                    full_filename = filename
                            except TypeError:
                                status_dict = {'id': id, 'url': img, 'wget': 'Unsupported URL', 'url3': False, 'pcurl': False}
                                status_list.append(status_dict)
                                logging.warning('Unsupported URL! '+img)
                                continue
                except:
                    status_dict = {'id': id, 'url': img, 'wget': 'Unsupported URL', 'url3': False, 'pcurl': False}
                    status_list.append(status_dict)
                    logging.warning('Unsupported URL! '+img)
                    continue
                try:
                    addr1 = socket.gethostbyname(domain)
                    try:
                        file_hash = get_file_hash(img)
                        if file_hash in hashes:
                            for h in hash_table:
                                if h['hash'] == file_hash:  #does not seem to detect symlink so using try except instead
                                    local_path = h['image_path']
                                    relative_path = os.path.relpath(local_path,out_path)
                                    if not os.path.islink(out_path):
                                        try:
                                            os.symlink(relative_path,out_path)
                                        except FileExistsError:
                                            print('Symbolic link already exists!')
                                            logging.warning('Symbolic link already exists! '+img)
                            continue
                    except Exception as e:
                        status_dict = {'id': id, 'url': img, 'wget': False, 'url3': e, 'pcurl': False}
                        status_list.append(status_dict)
                        logging.warning("Unable to get "+img+"'s file hash!")
                        continue
                    if not os.path.exists(os.path.join(img_dir,img.split('/')[-1])):
                       try:
                           wget.download(img,out=out_path)
                       except Exception as e:
                           status_dict = {'id': id, 'url': img, 'wget': e, 'url3': False, 'pcurl': False}
                           status_list.append(status_dict)
                           print("wget download failed! attempting download with urllib3.")
                           try:
                               pauseTime = random.randint(lowPauseTime, upPauseTime)
                               time.sleep(pauseTime)
                               download_image(out_path,img)
                           except Exception as e:
                               print(e)
                               print("urllib3 download failed! attempting download with pycurl.")                               
                               status_dict = {'id': id, 'url': img, 'wget': False, 'url3': e, 'pcurl': False}
                               status_list.append(status_dict)
                               try:
                                   downloadFile(img, out_path)
                               except Exception as e:
                                   print(e)
                                   print("pycurl download failed! attempting download with pycurl.")                               
                                   status_dict = {'id': id, 'url': img, 'wget': False, 'url3': False, 'pcurl': e}
                                   status_list.append(status_dict)
                               else:
                                   file_hash = downloadFile(img)
                                   hashes.append(file_hash)
                                   status_dict = {'id': id, 'url': img, 'wget': False, 'url3': False, 'pcurl': True}
                                   status_list.append(status_dict)
                           else:
                               file_hash = get_file_hash(out_path)
                               hashes.append(file_hash)
                               status_dict = {'id': id, 'url': img, 'wget': False, 'url3': True, 'pcurl': False}
                               status_list.append(status_dict)
                       else:
                           file_hash = get_file_hash(out_path)
                           hashes.append(file_hash)
                           status_dict = status_dict = {'id': id, 'url': img, 'wget': True, 'url3': False, 'pcurl': False}
                           status_list.append(status_dict)
                    pauseTime = random.randint(lowPauseTime, upPauseTime)
                    time.sleep(pauseTime)
                except Exception as e:
                    try:
                        download(img,img_dir)
					except Exception as e:
						status_dict = status_dict = {'id': id, 'url': img, 'wget': 'DNS lookup failed!', 'url3': False, 'pcurl': False}
						status_list.append(status_dict)
						logging.warning("Unable to get resolve hostname "+img)
						continue
					else:
                        status_dict = status_dict = {'id': id, 'url': img, 'wget': 'Unknown', 'url3': 'Unknown', 'pcurl': 'Unknown'}
                        status_list.append(status_dict)
						continue
    except KeyError:      
        print(id+" has no images!")
    except Exception as e:
        print(id+" experienced error "+e)
    else:
        print("Finished Processing Entry "+id+"!")
    return status_list

#prepopulate list for batch operations
accounts = []
if len(accounts) == 0:# Prompts user for Steem account for backup if account list not prepopulated. Creates respective user folder in backups if not exists 
    account = input("Account to Backup?")
    accounts.append(account)

def download_blogs(accounts,rounds):
    for account_to_backup in accounts:
        i = 0
        while i < rounds:
            results = []
            blog_list = get_blog_entries(account_to_backup)
            img_hash_list = get_image_hash_list(account_to_backup)
            hashes = []
            for h in img_hash_list:
                hashes.append(h['hash'])
            if not os.path.isdir(working_dir+"/Backups/"+account_to_backup):
                os.mkdir(working_dir+"/Backups/"+account_to_backup)
            for b in blog_list:
                stats = download_blog_entry(b,img_hash_list,hashes)
                for s in stats:
                    results.append(s)
            i += 1
		export_csv('SteemYaLater_'+account_to_backup+'_results_',results)

download_blogs(accounts,1) #runs backups on accounts w one iteration.
