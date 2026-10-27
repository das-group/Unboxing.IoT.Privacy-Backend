from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor
from typing import Literal
from logging import error, info
import requests
import traceback
import time

from src.onekey import Client, FirmwareMetadata
from src.config import DATA_SERVICE, ONEKEY_API_TOKEN, ONEKEY_API_URL
from pathlib import Path
import tempfile
import time

process_pool: ThreadPoolExecutor | None = None
is_running = True
client = None
default_product_group = None
default_analysis_configuration = None


def setup_onekey():
    
    # Setup ONEKEY
    client = Client(api_url=ONEKEY_API_URL)
    client.use_token(ONEKEY_API_TOKEN)
    
    GET_PRODUCT_GROUPS = """
    query {
      allProductGroups {
        id
        name
      }
    }
    """
    res = client.query(GET_PRODUCT_GROUPS)
    default_product_group = next(pg for pg in res["allProductGroups"] if pg["name"] == "Default")

    GET_ANALYSIS_CONFIGURATIONS = """
    query {
      allAnalysisConfigurations {
        id
        name
      }
    }
    """
    res = client.query(GET_ANALYSIS_CONFIGURATIONS)
    default_analysis_configuration = next(conf for conf in res["allAnalysisConfigurations"] if conf["name"] == "Default")
    
    return client, default_product_group, default_analysis_configuration


def start_processing_pool(max_workers: int):
    """Start the process pool for analysis tasks"""
    global process_pool
    if process_pool is None:
        process_pool = ThreadPoolExecutor(max_workers=max_workers) # ProcessPoolExecutor 
        
        process_pool.submit(analysis_task_watch_worker)
        
    
def stop_processing_pool(wait: bool):
    """Shut down the process pool"""
    global process_pool, is_running
    is_running = False
    if process_pool is not None:
        process_pool.shutdown(wait=wait, cancel_futures=True)
        process_pool = None
        

# This executes slow as shit
def submit_firmware_worker(
    user_id: str,
    entry_id: str,
    model_name: str,
    manufacturer_name: str,
    file_data
):
    try:
        client, default_product_group, default_analysis_configuration = setup_onekey()
        
        metadata = FirmwareMetadata(
            name=(str(manufacturer_name) + ' ' + str(model_name) + " @ "+str(user_id)),
            vendor_name=manufacturer_name,
            product_name=model_name,
            product_group_id=default_product_group["id"],
            analysis_configuration_id=default_analysis_configuration["id"],
            notes='Submitted by ' + user_id
        )
        
        with tempfile.NamedTemporaryFile(delete=False, suffix=".bin") as tmp:
            print('Uploading to ONEKEY...', flush=True)
            tmp.write(file_data)    
            tmp.flush()
            firmware_path = Path(tmp.name)
            res = client.upload_firmware(metadata, firmware_path, enable_monitoring=False)
            
            # {'id': 'd0a76748-5840-4c03-9b1e-8418e71989ac', 'filename': 'tmpkks3eef4.bin', 'sha256': 'd2ffa3fd92420eea59d2310146672d1f0f1eed51f59c43d286e7604fa1129bb6', 'size': 4096, 'metadata': {'name': 'user_0b5cea1b-7af4-44fb-bf74-dfc5fea1130b', 'version': None, 'notes': 'Submitted by 0b5cea1b-7af4-44fb-bf74-dfc5fea1130b', 'release_date': None, 'monitoring_enabled': False}}

            print('Submitted', res, flush=True)
            
            onekey_firmware_id = res['id']
            
            resp = requests.post(f"http://{DATA_SERVICE}/report/firmware/add", 
                json={
                    "entry_id": entry_id,
                    "firmware_id": onekey_firmware_id,
                    "analysis_id": None,
                    "status": 'PENDING',
                    "data": None
                })
            
            print('Posted', resp.text, flush=True)
    except Exception as e:
        error(f"[ERROR] Exception during analysis for entry_id: {entry_id}: {e}")
        print(traceback.format_exc(), flush=True)


def submit_analysis_task(
    user_id: str,
    entry_id: str,
    model_name: str,
    manufacturer_name: str,
    file_data
):
    assert process_pool is not None
    process_pool.submit(submit_firmware_worker, user_id, entry_id, model_name, manufacturer_name, file_data)


def analysis_task_watch_worker():
    
    print('Initializing ONEKEY API')
    
    start = time.time()
    client, default_product_group, default_analysis_configuration = setup_onekey()
    end = time.time()
    
    print('ONEKEY API init done in', end - start, 'seconds')
    
    while True:
        
        print('analysis_task_watch_worker is_running', client, default_analysis_configuration, default_product_group, flush=True)

        try:
            
            # Fetch firmware tasks 
            resp = requests.get(f"http://{DATA_SERVICE}/report/pending_firmware")
            entries_pending_firmware_analysis = resp.json()
            
            for entry in entries_pending_firmware_analysis:
                for firmware_entry in entry['firmware_reports']:
                    
                    GET_FIRMWARE_INFO = """
                    
                    fragment CWEFragment on CWE {
                        id
                        name
                        description
                    }

                    fragment ReferenceFragment on Reference {
                        title
                        url
                    }


                    fragment IssueFragment on Issue {
                      id
                      severity
                      confidence
                      type
                      summary
                      notes
                      status
                      isManual
                      file {
                        path 
                        name
                      }
                      doc {
                        type
                        summary
                        description
                        mitigation 
                        cwes {
                            ...CWEFragment
                        }
                        references{
                            ...ReferenceFragment
                        }
                      }
                    }


                    fragment AnalysisFragment on Analysis {
                      id
                      state
                      result
                    }

                    fragment CVEMatchEvidenceFragment on CVEMatchEvidence {
                      name
                      match
                      score
                      description
                      files
                    }

                    fragment CVEEntryFragment on CVEEntry {
                      id
                      description
                      name
                      cvss2 {
                        score
                        baseScore
                      }
                      cvss3 {
                        baseScore
                        overallScore
                      }
                      cvss4 {
                        baseScore
                      }
                      summary
                    }

                    fragment CVEMatchFragment on CVEMatch {
                      id
                      component {
                        key
                        name
                      }
                      cve {
                        ...CVEEntryFragment
                      }
                      score
                      evidences {
                        ...CVEMatchEvidenceFragment
                      }
                      originSeverity
                      vendorResponse
                      notes
                    }
                    
                    
                    fragment IpAddressFragment on IpAddress {
                      ipAddress
                      countryCode
                      autonomousSystemNumber
                      autonomousSystemOrganization
                    }

                    fragment URIFragment on URI {
                      id
                      uri
                      scheme
                      hostname
                      username
                      password
                      ipAddresses {
                          ...IpAddressFragment
                      }
                    }
                    
                    fragment PeripheralFragment on Peripheral {
                      id
                      type
                      typeHumanReadable
                      name
                      dtsPath
                      dtsLabel
                      category
                      status
                    }
                    
                    query firmware($id: ID!) {
                      firmware(id: $id) {
                        id
                        name
                        uploadTime
                        version
                        notes
                        totalSize
                        uploader
                        componentCount
                        labels
                        analyses {
                          ...AnalysisFragment
                        }
                        latestIssues {
                          ...IssueFragment
                        }
                        cveMatches {
                          ...CVEMatchFragment
                        }
                        uris {
                          ...URIFragment
                        }
                        peripherals {
                          ...PeripheralFragment
                        }
                        
                      }
                    }
                    """
                    # Fetch from onekey
                    firmware_info = client.query(GET_FIRMWARE_INFO, {"id": firmware_entry['id']})
                    
                    # print(firmware_info, flush=True)
                    
                    # Check if analysis is done
                    for analysis in firmware_info['firmware']['analyses']:
                        
                        # If state changed
                        if firmware_entry['status'] != analysis['state']:
                            
                            print('Sending post', flush=True)
                            
                            # print( firmware_info['firmware'], flush=True)
                            
                            # Update status in database
                            resp = requests.post(f"http://{DATA_SERVICE}/report/firmware/set", 
                                json={
                                    "entry_id": entry['_id'],
                                    "firmware_id": firmware_entry['id'],
                                    "analysis_id": analysis['id'],
                                    "status": analysis['state']
                                })
                            
                            if analysis['state'] == 'DONE':
                                # Add to reports database
                                resp = requests.post(f"http://{DATA_SERVICE}/report/firmware", 
                                    json={
                                        "entry_id": entry['_id'],
                                        "user_id": entry['created_by_user_id'],
                                        "report_id": firmware_entry['id'],
                                        "report": { 
                                            'issues': firmware_info['firmware']['latestIssues'],
                                            'cves': firmware_info['firmware']['cveMatches'],
                                            'uris': firmware_info['firmware']['uris'],
                                            'peripherals': firmware_info['firmware']['peripherals']
                                        }
                                    })
                            
                            print('Updated entry', flush=True)
                            
                    print('From ' + firmware_entry['id'], firmware_info, flush=True)
        except Exception as e:
            error(f"[ERROR] Exception in analysis_task_watch_worker", e)
            print(e, flush=True)
        
        time.sleep(30)



