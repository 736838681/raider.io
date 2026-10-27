import unittest
import raiderio_armor_compare as a


def player(c,s,n,ids):
    return {'class':c,'spec':s,'name':n,'region':'cn','realm':'chillwind-point',
            'source_score':500,'items':{slot:{'id':v,'name':f'Item {v}'} for (slot,_),v in zip(a.SLOTS,ids)}}

class OfflineTests(unittest.TestCase):
    def test_run_roster_format(self):
        m={'character':{'name':'战士测试','class':{'slug':'warrior'},
                        'spec':{'slug':'protection'},'region':{'slug':'cn'},
                        'realm':{'slug':'chillwind-point'}},'role':'tank'}
        r=a.read_member(m,'cn',519.5)
        self.assertEqual((r['class'],r['spec'],r['region']),('warrior','protection','cn'))
    def test_armor_slots(self):
        items={k:{'item_id':i,'name':'X'+k} for i,(k,_) in enumerate(a.SLOTS,1000)}
        items['neck']={'item_id':999999}
        self.assertEqual(len(a.get_items({'gear':{'items':items}})),9)
        self.assertNotIn('neck',a.get_items({'gear':{'items':items}}))
    def test_same_modal_count(self):
        base=list(range(100,109))
        other=[100,101,102,103,104,105,106,207,208]
        people=[player('warrior','protection','T'+str(i),base) for i in range(3)]
        people += [player('warrior','arms','D'+str(i),other) for i in range(3)]
        ranked,details,groups=a.summaries(people,3)
        row=next(r for r in ranked if r['组合']=='防护战士＋武器战士')
        self.assertEqual(row['相同防具件数_主流ID'],7)
        pal=next(r for r in ranked if r['组合']=='防护骑士＋惩戒骑士')
        self.assertEqual(pal['相同防具件数_主流ID'],'')
        self.assertEqual(pal['状态'],'样本不足_不排名')
    def test_active_spec_mismatch_fails(self):
        class Mock:
            def get(self,*args):
                return {'class':'Warrior','active_spec_name':'Fury','gear':{'items':{slot:{'item_id':i+1} for i,(slot,_) in enumerate(a.SLOTS)}}}
        p={'region':'cn','realm':'server','name':'test','class':'warrior','spec':'protection'}
        with self.assertRaises(ValueError):
            a.profile_player(Mock(),p)

if __name__=='__main__':
    unittest.main()
